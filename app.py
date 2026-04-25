from email_service import send_otp_email, send_purchase_confirmation_email
from models import Product, User, Order, OrderItem, OTPLogin, ProductFile, Review, Category
from flask_migrate import Migrate
from admin import setup_admin
from config import Config
from extensions import db
from http.client import HTTPException
import os
import sys
import stripe
import secrets
import hmac
import requests
from datetime import datetime, timedelta, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, session, redirect, url_for, flash, send_file, abort, jsonify
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate = Migrate(app, db)
    setup_admin(app)
    csrf.init_app(app)
    limiter.init_app(app)

    def get_current_user():
        user_id = session.get('user_id')
        return User.query.get(user_id) if user_id else None

    def user_has_purchased(product_id):
        user = get_current_user()
        if not user:
            return False
        return OrderItem.query.join(Order).filter(
            Order.user_id == user.id,
            Order.status == 'paid',
            OrderItem.product_id == product_id
        ).first() is not None

    def get_user_purchased_product_ids():
        user = get_current_user()
        if not user:
            return set()
        return {item.product_id for item in OrderItem.query.join(Order).filter(
            Order.user_id == user.id,
            Order.status == 'paid'
        ).all()}

    os.makedirs(app.config['UPLOAD_FOLDER_FILES'], exist_ok=True)
    os.makedirs(app.config['UPLOAD_FOLDER_IMAGES'], exist_ok=True)

    with app.app_context():
        db.create_all()

    # Routes
    @app.route('/')
    def index():
        stats = {
            "total_products": Product.query.count(),
            "total_users": User.query.count(),
            "total_orders": Order.query.filter_by(status='paid').count(),
            "average_rating": db.session.query(db.func.avg(Review.rating)).scalar() or 0,
            "lowest_price": db.session.query(db.func.min(Product.price_cents)).scalar() or 0,
        }
        few_reviews = Review.query.order_by(
            Review.created_at.desc()).limit(10).all()
        products = (Product.query.filter_by(is_active=True).order_by(
            Product.created_at.desc()).limit(4).all())
        categories = Category.query.order_by(Category.name).all()
        return render_template('index.html', products=products, stats=stats, few_reviews=few_reviews, categories=categories)

    @app.route('/product/<int:product_id>')
    def product(product_id):
        product = Product.query.get_or_404(product_id)
        reviews = product.reviews
        current_user = get_current_user()
        purchased = user_has_purchased(product_id)
        in_cart = product_id in session.get('cart', [])
        suggested_products = Product.query.filter(Product.category_id == product.category_id, Product.id !=
                                                  product.id, Product.is_active == True).limit(4).all() if product.category_id else []
        return render_template(
            'product.html',
            product=product,
            reviews=reviews,
            purchased=purchased,
            in_cart=in_cart,
            current_user=current_user,
            suggested_products=suggested_products
        )

    @app.route('/category/<int:category_id>')
    def category(category_id):
        category = Category.query.get_or_404(category_id)
        products = Product.query.filter_by(
            category_id=category_id, is_active=True).all()
        return render_template('category.html', category=category, products=products)

    @app.route('/products')
    def products():
        # Get filter and sort parameters
        category_id = request.args.get('category', type=int)
        min_price = request.args.get('min_price', type=float, default=0)
        max_price = request.args.get('max_price', type=float)
        sort_by = request.args.get('sort', default='newest')
        
        # Build query
        query = Product.query.filter_by(is_active=True)
        
        if category_id:
            query = query.filter_by(category_id=category_id)
        
        if max_price:
            max_price_cents = int(max_price * 100)
            min_price_cents = int(min_price * 100)
            query = query.filter(Product.price_cents >= min_price_cents, Product.price_cents <= max_price_cents)
        else:
            min_price_cents = int(min_price * 100)
            query = query.filter(Product.price_cents >= min_price_cents)
        
        products_list = query.all()
        
        # Sort products
        if sort_by == 'price_asc':
            products_list.sort(key=lambda p: p.price_cents)
        elif sort_by == 'price_desc':
            products_list.sort(key=lambda p: p.price_cents, reverse=True)
        elif sort_by == 'name_asc':
            products_list.sort(key=lambda p: p.title.lower())
        elif sort_by == 'rating_desc':
            products_list.sort(key=lambda p: p.avg_rating, reverse=True)
        elif sort_by == 'newest':
            products_list.sort(key=lambda p: p.created_at, reverse=True)
        
        # Get all categories for filter
        categories = Category.query.order_by(Category.name).all()
        
        # Calculate min and max prices for filter display
        all_products = Product.query.filter_by(is_active=True).all()
        min_product_price = min((p.price_cents for p in all_products), default=0) / 100
        max_product_price = max((p.price_cents for p in all_products), default=0) / 100
        
        return render_template(
            'products.html',
            products=products_list,
            categories=categories,
            selected_category=category_id,
            min_price=min_price,
            max_price=max_price or max_product_price,
            sort_by=sort_by,
            min_product_price=min_product_price,
            max_product_price=max_product_price
        )

    @app.route('/cart', methods=['GET', 'POST'])
    def cart():
        current_user = get_current_user()
        if request.method == 'POST':
            product_id = request.form.get('product_id')
            if product_id:
                product_id = int(product_id)
                cart_items = session.get('cart', [])
                if current_user and user_has_purchased(product_id):
                    flash(
                        'Vous possédez déjà ce produit, il ne peut donc pas être ajouté au panier.')
                elif product_id in cart_items:
                    flash('Le produit est déjà dans votre panier.')
                else:
                    cart_items.append(product_id)
                    session['cart'] = cart_items
                    flash('Le produit a été ajouté à votre panier !')
            return redirect(url_for('cart'))

        cart_items = session.get('cart', [])
        if current_user and cart_items:
            purchased_ids = get_user_purchased_product_ids()
            filtered = [pid for pid in cart_items if pid not in purchased_ids]
            if len(filtered) != len(cart_items):
                session['cart'] = filtered
                cart_items = filtered
                if filtered:
                    flash(
                        'Nous avons retiré de votre panier les articles que vous possédez déjà.')
                else:
                    flash('Votre panier contenait des produits que vous possédez déjà.')
        products_in_cart = Product.query.filter(
            Product.id.in_(cart_items)).all() if cart_items else []
        total_cents = sum(p.price_cents for p in products_in_cart)

        return render_template('cart.html', products=products_in_cart, total=total_cents / 100)

    @app.route('/cart/remove/<int:product_id>', methods=['POST'])
    def cart_remove(product_id):
        cart_items = session.get('cart', [])
        if product_id in cart_items:
            cart_items.remove(product_id)
            session['cart'] = cart_items
            flash('Produit retiré du panier.')
        return redirect(url_for('cart'))

    @app.route('/checkout', methods=['GET', 'POST'])
    def checkout():
        stripe.api_key = app.config['STRIPE_SECRET_KEY']
        current_user = get_current_user()
        cart_items = session.get('cart', [])
        if not cart_items:
            flash('Votre panier est vide.')
            return redirect(url_for('cart'))

        if current_user and cart_items:
            purchased_ids = get_user_purchased_product_ids()
            filtered = [pid for pid in cart_items if pid not in purchased_ids]
            if not filtered:
                session.pop('cart', None)
                flash('Tous les articles de votre panier ont déjà été achetés.')
                return redirect(url_for('cart'))
            if len(filtered) != len(cart_items):
                session['cart'] = filtered
                cart_items = filtered
                flash(
                    'Nous avons retiré de votre panier les articles que vous possédez déjà.')

        products_in_cart = Product.query.filter(
            Product.id.in_(cart_items)).all()
        if not products_in_cart:
            flash('Votre panier est vide.')
            return redirect(url_for('cart'))

        if request.method == 'POST':
            if current_user:
                email = current_user.email
                first_name = current_user.first_name
            else:
                email = request.form.get('email')
                first_name = request.form.get('first_name')

            if User.query.filter_by(email=email).first() and not current_user:
                flash(
                    'Un compte avec cet email existe déjà. Veuillez vous connecter pour continuer.')
                return redirect(url_for('login'))

            line_items = []
            for p in products_in_cart:
                print(url_for('static', filename='uploads/images/' +
                      p.images[0].image_path, _external=True))
                line_items.append({
                    'price_data': {
                        'currency': 'EUR',
                        'product_data': {
                            'name': p.title,
                            'description': p.description[:200],
                            'images': [url_for('static', filename='uploads/images/' + p.images[0].image_path, _external=True)] if p.images else [],
                        },
                        'unit_amount': p.price_cents,
                    },
                    'quantity': 1,
                })

            try:
                checkout_session = stripe.checkout.Session.create(
                    customer_email=email,
                    payment_method_types=['card'],
                    line_items=line_items,
                    mode='payment',
                    success_url=url_for(
                        'success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
                    cancel_url=url_for('cart', _external=True),
                    metadata={
                        'first_name': first_name,
                        'product_ids': ','.join(map(str, cart_items))
                    }
                )
                return redirect(checkout_session.url, code=303)
            except Exception as e:
                flash(
                    "Une erreur est survenue. Veuillez contacter le support (support@fxshop.com).")
                print(f"Stripe checkout error: {e}", file=sys.stderr)
                return redirect(url_for('cart'))

        return render_template('checkout.html', user=current_user)

    stripe_client = stripe.StripeClient(app.config['STRIPE_SECRET_KEY'])

    @app.route('/webhook/stripe', methods=['POST'])
    @csrf.exempt
    def stripe_webhook():
        try:
            payload = request.get_data()
            sig_header = request.headers.get('Stripe-Signature')
            webhook_secret = app.config['STRIPE_WEBHOOK_SECRET']

            try:
                event = stripe_client.construct_event(
                    payload, sig_header, webhook_secret)
            except ValueError:
                return jsonify({'error': 'Invalid payload'}), 400
            except stripe.error.SignatureVerificationError:
                return jsonify({'error': 'Invalid signature'}), 400

            if event['type'] == 'checkout.session.completed':
                session = event['data']['object']

                if session['payment_status'] != 'paid':
                    return jsonify({'status': 'ignored'}), 200

                session_id = session['id']
                amount_total = session['amount_total']

                customer_details = session['customer_details']
                email = customer_details['email']

                metadata = session['metadata'] or {}
                first_name = metadata['first_name']
                product_ids_str = metadata['product_ids']

                if not email or not product_ids_str:
                    return jsonify({'error': 'Missing data'}), 400

                existing_order = Order.query.filter_by(
                    stripe_session_id=session_id).first()
                if existing_order:
                    return jsonify({'status': 'already_processed'}), 200

                try:
                    user = User.query.filter_by(email=email).first()
                    if not user:
                        user = User(email=email, first_name=first_name)
                        db.session.add(user)
                        db.session.flush()

                    new_order = Order(
                        user_id=user.id,
                        status='paid',
                        total_price_cents=amount_total,
                        stripe_session_id=session_id
                    )
                    db.session.add(new_order)
                    db.session.flush()

                    product_ids = product_ids_str.split(',')
                    for p_id in product_ids:
                        product = db.session.get(Product, int(p_id))
                        if product:
                            db.session.add(OrderItem(
                                order_id=new_order.id,
                                product_id=product.id,
                                price_at_time_cents=product.price_cents
                            ))

                    db.session.commit()

                except Exception as e:
                    db.session.rollback()
                    app.logger.error(f"DB error: {e}")
                    return jsonify({'error': 'Database error'}), 500

                try:
                    items = []
                    for p_id in product_ids:
                        product = db.session.get(Product, int(p_id))
                        if product:
                            items.append(
                                {'title': product.title, 'price_cents': product.price_cents})
                    send_purchase_confirmation_email(
                        email, {'items': items, 'total_price_cents': amount_total})
                except Exception as e:
                    app.logger.error(f"Email error: {e}")

            return jsonify({'status': 'ok'}), 200
        except Exception as e:
            app.logger.error(f"Webhook processing error: {e}")
            return jsonify({'error': 'Server error'}), 500

    @app.route('/success')
    def success():
        session_id = request.args.get('session_id')
        if not session_id:
            return redirect(url_for('index'))

        import time
        for _ in range(5):
            order = Order.query.filter_by(stripe_session_id=session_id).first()
            if order:
                break
            time.sleep(1)

        if not order:
            flash(
                "Votre paiement est en cours de traitement. Vos achats apparaîtront dans quelques instants.")
            return redirect(url_for('index'))

        session['user_id'] = order.user_id
        session.pop('cart', None)
        flash('Paiement réussi !')
        return redirect(url_for('purchases'))

    @app.route('/login', methods=['GET', 'POST'])
    @limiter.limit("10 per minute")
    def login():
        print("Login route accessed.", file=sys.stderr)
        if request.method == 'POST':
            email = request.form.get('email')
            user = User.query.filter_by(email=email).first()
            if not user:
                flash('Account not found. Please purchase a product first.')
                return redirect(url_for('login'))

            OTPLogin.query.filter_by(email=email).delete()

            otp_code = str(secrets.randbelow(900000) + 100000)
            expires_at = datetime.utcnow() + timedelta(minutes=10)
            otp_entry = OTPLogin(email=email, otp_code_hash=generate_password_hash(
                otp_code), expires_at=expires_at, attempts=0)
            db.session.add(otp_entry)
            db.session.commit()

            if send_otp_email(email, otp_code):
                flash('Un OTP a été envoyé à votre email.')
            else:
                flash(
                    'L\'envoi de l\'e-mail contenant le mot de passe à usage unique a échoué. Veuillez réessayer.')
                return redirect(url_for('login'))

            return redirect(url_for('otp_verify', email=email))

        return render_template('login.html')

    @app.route('/otp_verify', methods=['GET', 'POST'])
    @limiter.limit("15 per minute")
    def otp_verify():
        email = request.args.get('email')
        if request.method == 'POST':
            otp = request.form.get('otp')
            email = request.form.get('email')

            otp_entry = OTPLogin.query.filter_by(
                email=email).order_by(OTPLogin.id.desc()).first()
            if not otp_entry or otp_entry.expires_at < datetime.utcnow():
                flash('Code à usage unique non valide ou périmé.')
                return redirect(url_for('otp_verify', email=email))

            if otp_entry.attempts >= 5:
                flash(
                    'Trop de tentatives incorrectes. Veuillez demander un nouveau code.')
                OTPLogin.query.filter_by(email=email).delete()
                db.session.commit()
                return redirect(url_for('login'))

            if not check_password_hash(otp_entry.otp_code_hash, otp):
                otp_entry.attempts += 1
                db.session.commit()
                flash('Code incorrect.')
                return redirect(url_for('otp_verify', email=email))

            user = User.query.filter_by(email=email).first()
            if user:
                session['user_id'] = user.id
                OTPLogin.query.filter_by(email=email).delete()
                db.session.commit()
                flash('Connexion réussie.')
                return redirect(url_for('purchases'))

        return render_template('otp_verify.html', email=email)

    @app.route('/logout')
    def logout():
        session.pop('user_id', None)
        flash('Déconnecté.')
        return redirect(url_for('index'))

    @app.route('/account')
    def account():
        current_user = get_current_user()
        if not current_user:
            return redirect(url_for('login'))
        return render_template('account.html', user=current_user)

    @app.route('/orders')
    def orders():
        current_user = get_current_user()
        if not current_user:
            return redirect(url_for('login'))
        orders = Order.query.filter_by(user_id=current_user.id, status='paid').order_by(
            Order.created_at.desc()).all()
        return render_template('orders.html', orders=orders)

    @app.route('/purchases')
    def purchases():
        user_id = session.get('user_id')
        if not user_id:
            return redirect(url_for('login'))

        user = User.query.get(user_id)
        orders = Order.query.filter_by(user_id=user_id, status='paid').all()
        purchased_items = []
        for order in orders:
            for item in order.items:
                purchased_items.append(item.product)

        return render_template('purchases.html', products=set(purchased_items))

    @app.route('/download/<int:product_id>')
    def download(product_id):
        user_id = session.get('user_id')
        if not user_id:
            return redirect(url_for('login'))

        order_item = OrderItem.query.join(Order).filter(
            Order.user_id == user_id,
            Order.status == 'paid',
            OrderItem.product_id == product_id
        ).first()

        if not order_item:
            abort(403)

        product_file = ProductFile.query.filter_by(
            product_id=product_id).first()
        if not product_file:
            abort(404)

        if not os.path.exists(os.path.join(app.config.get('UPLOAD_FOLDER_FILES'), product_file.file_path)):
            abort(404)

        return send_file(os.path.join(app.config.get('UPLOAD_FOLDER_FILES'), product_file.file_path), as_attachment=True)

    @app.route('/product/<int:product_id>/review', methods=['POST'])
    def product_review(product_id):
        user_id = session.get('user_id')
        if not user_id:
            flash("Vous devez être connecté pour évaluer un produit.")
            return redirect(url_for('login'))

        rating = int(request.form.get('rating', 5))
        comment = request.form.get('comment', '')

        order_item = OrderItem.query.join(Order).filter(
            Order.user_id == user_id,
            Order.status == 'paid',
            OrderItem.product_id == product_id
        ).first()

        if not order_item:
            flash("Vous ne pouvez évaluer que les produits que vous avez achetés.")
            return redirect(url_for('product', product_id=product_id))

        if Review.query.filter_by(user_id=user_id, product_id=product_id).first():
            flash("Vous avez déjà évalué ce produit.")
            return redirect(url_for('product', product_id=product_id))

        review = Review(product_id=product_id, user_id=user_id,
                        rating=rating, comment=comment)
        db.session.add(review)
        db.session.commit()
        flash("Merci pour votre avis !")
        return redirect(url_for('product', product_id=product_id))

    @app.route('/terms')
    def terms():
        return render_template('terms.html')

    @app.route('/admin/login', methods=['GET', 'POST'])
    @limiter.limit("5 per minute")
    def admin_login():
        if request.method == 'POST':
            password = request.form.get('password')

            if password and hmac.compare_digest(password.encode('utf-8'), Config.ADMIN_PASSWORD.encode('utf-8')):
                session['admin_logged_in'] = True
                return redirect('/admin')

        return render_template('admin_login.html')

    @app.route('/admin/logout')
    def admin_logout():
        session.pop('admin_logged_in', None)
        return redirect(url_for('index'))

    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", code=404, error=e), 404


    @app.errorhandler(HTTPException)
    def http_error(e):
        return render_template("error.html", code=e.code, error=e), e.code


    @app.errorhandler(Exception)
    def internal_error(e):
        app.logger.exception(
            f"Error on {request.method} {request.path} | IP: {request.remote_addr}"
        )
        return render_template("error.html", code=500, error=e), 500

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=5000)
