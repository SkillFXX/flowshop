import smtplib
import html2text
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app, render_template, url_for

def send_email(to_email, subject, html_content, text_content=None):
    """Send an email using SMTP configuration from Flask app config."""
    try:
        if text_content is None:
            converter = html2text.HTML2Text()
            converter.ignore_links = False  
            converter.body_width = 0       
            text_content = converter.handle(html_content)

        # Configuration SMTP
        mail_server = current_app.config.get('MAIL_SERVER')
        mail_port = current_app.config.get('MAIL_PORT')
        mail_username = current_app.config.get('MAIL_USERNAME')
        mail_password = current_app.config.get('MAIL_PASSWORD')
        mail_default_sender = current_app.config.get('MAIL_DEFAULT_SENDER')
        mail_use_tls = current_app.config.get('MAIL_USE_TLS')
        mail_use_ssl = current_app.config.get('MAIL_USE_SSL')

        if not all([mail_server, mail_port, mail_username, mail_password]):
            current_app.logger.warning("Email configuration incomplete. Skipping.")
            return False

        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = mail_default_sender or mail_username
        msg['To'] = to_email

        msg.attach(MIMEText(text_content, 'plain'))
        msg.attach(MIMEText(html_content, 'html'))

        if mail_use_ssl:
            server = smtplib.SMTP_SSL(mail_server, mail_port, timeout=15)
        else:
            server = smtplib.SMTP(mail_server, mail_port, timeout=15)
            if mail_use_tls:
                server.starttls()
        
        server.login(mail_username, mail_password)
        server.sendmail(msg['From'], [to_email], msg.as_string())
        server.quit()

        current_app.logger.info(f"Email sent successfully to {to_email}")
        return True

    except Exception as e:
        current_app.logger.error(f"Failed to send email to {to_email}: {e}")
        return False

def send_otp_email(email, otp_code):
    subject = "Votre code de connexion"
    html_content = render_template("emails/otp.html", otp_code=otp_code)
    
    return send_email(email, subject, html_content)

def send_purchase_confirmation_email(email, order_details):
    subject = "Confirmation d'achat - SkillFX Shop"
    
    html_content = render_template(
        "emails/purchase.html",
        order=order_details,
        base_url=current_app.config.get("SERVER_NAME", "http://localhost:5000")
    )

    return send_email(email, subject, html_content)