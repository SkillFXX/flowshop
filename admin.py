from flask import app, redirect, render_template, url_for, request, session
from flask_admin import Admin, AdminIndexView, expose
from flask_admin.menu import MenuLink
from flask_admin.contrib.sqla import ModelView
from flask_admin.form.upload import FileUploadField
import os
from werkzeug.utils import secure_filename
from models import User, Product, ProductImage, ProductFile, Order, OrderItem, Review, Category
from extensions import db
from config import Config

class SecuredAdminIndexView(AdminIndexView):
    def is_accessible(self):
        return session.get('admin_logged_in', False)

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('admin_login'))

class SecuredModelView(ModelView):
    def is_accessible(self):
        return session.get('admin_logged_in', False)

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('admin_login'))

class ProductModelView(SecuredModelView):
    form_columns = ['title', 'description', 'price_cents', 'category', 'is_active']
    column_list = ['title', 'category', 'price_cents', 'is_active']

class ProductImageModelView(SecuredModelView):
    form_columns = ['product', 'image_path']
    form_overrides = {
        'image_path': FileUploadField
    }
    form_args = {
        'image_path': {
            'label': 'Image',
            'base_path': Config.UPLOAD_FOLDER_IMAGES,
            'allowed_extensions': ['jpg', 'jpeg', 'png', 'gif', 'webp', 'avif']
        }
    }

class ProductFileModelView(SecuredModelView):
    form_columns = ['product', 'file_path', 'filename']
    column_list = ['product', 'file_path', 'filename']
    form_overrides = {
        'file_path': FileUploadField
    }
    form_args = {
        'file_path': {
            'label': 'File',
            'base_path': Config.UPLOAD_FOLDER_FILES,
        }
    }

def setup_admin(app):
    admin = Admin(app, name='SkillFX Shop Admin', index_view=SecuredAdminIndexView())
    admin.add_view(ProductModelView(Product, db.session))
    admin.add_view(SecuredModelView(Category, db.session))
    admin.add_view(ProductFileModelView(ProductFile, db.session))
    admin.add_view(ProductImageModelView(ProductImage, db.session))
    admin.add_view(SecuredModelView(User, db.session))
    admin.add_view(SecuredModelView(Order, db.session))
    admin.add_view(SecuredModelView(Review, db.session))

    admin.add_link(MenuLink(name='Logout', category='', url='/admin/logout'))
