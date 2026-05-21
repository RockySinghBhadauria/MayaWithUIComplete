"""Unified email notification for parsing results."""
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pandas as pd

import config
from core.logging_config import get_logger
from mailer.templates import build_summary_email

logger = get_logger('mailer')


class Notifier(object):
    """Sends parsing summary emails."""

    def __init__(self, db):
        self.db = db

    def run(self):
        """Send parsing summary email. Returns status dict."""
        logger.info("Preparing parsing summary email")

        # Get today's parsing summary
        try:
            from core.database import cast_date_sql, today_date_sql
            summary_df = self.db.fetch_df(
                "SELECT Company_ID, CompanyName, FiscalYear, CIK, Symbol, "
                "       Fortune_1000, Russell_3000, MDG_Client, "
                "       SCT_Parsed, Officer_Parsed, Vested_Parsed, "
                "       Outstanding_Equity_Parsed, PBA_Parsed, "
                "       FiledDate, Link, Parsed_Date "
                "FROM Maya_Parsing_Summary "
                "WHERE {} = {} "
                "ORDER BY SCT_Parsed DESC".format(
                    cast_date_sql("Parsed_Date"), today_date_sql())
            )
        except Exception as e:
            logger.error("Failed to fetch summary: %s", e)
            return {'status': 'failed', 'error': str(e)}

        if summary_df.empty:
            logger.info("No records parsed today — skipping email")
            return {'status': 'skipped', 'reason': 'no records today'}

        # Split into parsed vs not-parsed (canonical status strings: 'Parsed', 'No Table found',
        # 'Already Exist' are all considered "successful outcomes"; only 'Not Parsed' is failure)
        success_states = ['Parsed', 'No Table found', 'Already Exist']
        parsed = summary_df[summary_df['SCT_Parsed'].isin(success_states)]
        not_parsed = summary_df[~summary_df['SCT_Parsed'].isin(success_states)]

        # Build email HTML
        html_body = build_summary_email(parsed, not_parsed)

        # Send email
        if not config.SMTP_PASSWORD or not config.SMTP_TO:
            logger.warning("SMTP not configured (set MAYA_SMTP_PASSWORD and MAYA_SMTP_TO env vars)")
            logger.info("Email preview:\n%s", html_body[:500])
            return {
                'status': 'skipped',
                'reason': 'SMTP not configured',
                'parsed_count': len(parsed),
                'not_parsed_count': len(not_parsed),
            }

        try:
            self._send_email(html_body, len(summary_df))
            return {
                'status': 'sent',
                'parsed_count': len(parsed),
                'not_parsed_count': len(not_parsed),
            }
        except Exception as e:
            logger.error("Failed to send email: %s", e)
            return {'status': 'failed', 'error': str(e)}

    def _send_email(self, html_body, company_count):
        """Send the HTML email via SMTP."""
        msg = MIMEMultipart('alternative')
        msg['Subject'] = 'MAYA Parsing Summary - {} companies'.format(company_count)
        msg['From'] = config.SMTP_SENDER
        msg['To'] = config.SMTP_TO
        if config.SMTP_CC:
            msg['Cc'] = config.SMTP_CC

        msg.attach(MIMEText(html_body, 'html'))

        server = smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT)
        server.starttls()
        server.login(config.SMTP_SENDER, config.SMTP_PASSWORD)

        recipients = [config.SMTP_TO]
        if config.SMTP_CC:
            recipients.append(config.SMTP_CC)

        server.sendmail(config.SMTP_SENDER, recipients, msg.as_string())
        server.quit()
        logger.info("Summary email sent to %s", config.SMTP_TO)
