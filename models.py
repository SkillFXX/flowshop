import uuid
import datetime
from extensions import db

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    first_name = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    
    orders = db.relationship('Order', backref='user', lazy=True)
    reviews = db.relationship('Review', backref='user', lazy=True)

    def __repr__(self):
        return f"{self.first_name} ({self.email})"

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price_cents = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id', name='fk_product_category'), nullable=True)

    images = db.relationship('ProductImage', backref='product', lazy=True, cascade='all, delete-orphan')
    files = db.relationship('ProductFile', backref='product', lazy=True, cascade='all, delete-orphan')
    reviews = db.relationship('Review', backref='product', lazy=True, cascade='all, delete-orphan')
    category = db.relationship('Category', backref='products', lazy=True)
    
    @property
    def formatted_price(self):
        return f"{self.price_cents / 100:.2f}"
    
    def __repr__(self):
        return self.title

class ProductImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    image_path = db.Column(db.String(255), nullable=False)
    
    def __repr__(self):
        return f"Image for {self.product.title}"
    
class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return self.name

class ProductFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    filename = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return self.filename

class Order(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    stripe_session_id = db.Column(db.String(255), unique=True, nullable=True)
    status = db.Column(db.String(20), default='pending') 
    total_price_cents = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f"Order {self.id[:8]}... ({self.status})"

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.String(36), db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    price_at_time_cents = db.Column(db.Integer, nullable=False)
    product = db.relationship('Product', backref='order_items', lazy=True)

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False) 
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class OTPLogin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    otp_code_hash = db.Column(db.String(128), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    attempts = db.Column(db.Integer, default=0, nullable=False)
