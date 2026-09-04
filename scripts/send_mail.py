#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mail the generated dashboard. Skipped silently when SMTP secrets are absent."""
import os
import smtplib
import ssl
import sys
from email.header import Header
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate

host = os.environ.get("SMTP_HOST", "")
port = int(os.environ.get("SMTP_PORT", "465"))
user = os.environ.get("SMTP_USER", "")
passwd = os.environ.get("SMTP_PASS", "")
to_raw = os.environ.get("MAIL_TO", "")
html_path = sys.argv[1] if len(sys.argv) > 1 else "dist/index.html"

if not all([host, user, passwd, to_raw]):
    print("SMTP secrets not configured - skipping email (Pages output is unaffected).")
    sys.exit(0)

to_list = [a.strip() for a in to_raw.replace(";", ",").split(",") if a.strip()]

with open(html_path, "rb") as f:
    raw = f.read()

subject = os.environ.get("MAIL_SUBJECT", "AI 晨报")
msg = MIMEMultipart()
msg["From"] = user
msg["To"] = ", ".join(to_list)
msg["Subject"] = Header(subject, "utf-8")
msg["Date"] = formatdate(localtime=True)

# inline body first, so a mail client that blocks attachments still shows something
try:
    msg.attach(MIMEText(raw.decode("utf-8"), "html", "utf-8"))
except UnicodeDecodeError:
    msg.attach(MIMEText("晨报见附件。", "plain", "utf-8"))

part = MIMEApplication(raw, _subtype="html")
part.add_header("Content-Disposition", "attachment",
                filename=os.path.basename(html_path))
msg.attach(part)

ctx = ssl.create_default_context()
if port == 465:
    server = smtplib.SMTP_SSL(host, port, context=ctx, timeout=60)
else:
    server = smtplib.SMTP(host, port, timeout=60)
    server.starttls(context=ctx)

with server:
    server.login(user, passwd)
    server.sendmail(user, to_list, msg.as_string())

print(f"sent to {len(to_list)} recipient(s): {', '.join(to_list)}")
