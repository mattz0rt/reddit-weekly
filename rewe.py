#!/bin/python3

import praw
import smtplib
import requests
import parsel
import re
import io
import json
import os
import datetime
import sys
import itertools
import arrow
from urllib.parse import urlparse

from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from argparse import ArgumentParser
from premailer import Premailer

HEADERS = requests.utils.default_headers()
HEADERS.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:52.0) Gecko/20100101 Firefox/52.0'})

SCRIPT_PATH = os.path.dirname(os.path.realpath(__file__))
REDDIT_CSS = os.path.join(SCRIPT_PATH, 'css', 'reddit.css')

SUBREDDIT_HEADER = "<h1>/r/{subreddit}</h1>"
SUBMISSION = """<div class="DIV_2">
    <p class="P_3"><a href="{url}" class="A_4">{title}</a> <span class="SPAN_5">(<a href="" class="A_6">{domain}</a>)</span></p>
        <p class="P_8">submitted <time class="TIME_9">{time}</time> by <a href="https://www.reddit.com/user/{user}" class="A_10">{user}</a><span class="SPAN_11"></span><span class="SPAN_12"></span> <a href="{shortlink}" rel="nofollow" class="A_15">{num_comments} comments</a></p>
        </div>"""

def _concat_css(input_name, output):
    with open(input_name, encoding='utf-8') as f:
        output.write('\n<style>\n')
        output.write(f.read())
        output.write('\n</style>\n')

def _extract_external_css(selector):
    for p in selector.xpath("/html/head/link[@rel='stylesheet']"):
            href = re.sub(r"^//", r"https://", p.xpath("@href").extract_first())
            sheet = requests.get(href, headers=HEADERS).text if href else ""
            yield sheet

def weekly_page_header(file, css=None):
    if isinstance(file, str):
        with open(file, 'w', encoding='utf-8') as f:
            return weekly_page_header(file=f, css=css)

    file.write('<!DOCTYPE html>')
    file.write('<html>')

    if css == 1: # Download External
        file.write('<head>')
        file.write('<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">')
        for stylesheet in _extract_external_css(sel):
                file.write('\n<style>\n')
                file.write(stylesheet)
                file.write('\n</style>\n')
        file.write('</head>')
    elif css == 2: # Keep External
        head = sel.xpath("/html/head").extract_first()
        head = re.sub(r'="//', '="https://', head)
        file.write(head)
    elif isinstance(css, str):
        file.write('<head>')
        file.write('<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">')
        _concat_css(css, file)
        file.write('</head>')
    elif isinstance(css, list):
        file.write('<head>')
        file.write('<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">')
        for c in css:
            _concat_css(c, file)
        file.write('</head>')
    else:
        file.write('<head>')
        file.write('<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">')
        file.write('</head>')

    file.write('<body class="">')

    return file

def weekly_page(praw_inst, subreddit, file):
    print("Getting submissions for {}".format(subreddit))
    file.write(SUBREDDIT_HEADER.format(subreddit=subreddit))
    for submission in praw_inst.subreddit(subreddit).top('week', limit=3):
        file.write(SUBMISSION.format(
            url=submission.url,
            title=submission.title,
            domain=urlparse(submission.url).netloc,
            time=arrow.get(submission.created_utc).humanize(),
            user=submission.author.name,
            shortlink=submission.shortlink,
            num_comments=submission.num_comments,
        ))

def weekly_page_footer(file):
    file.write('</body>')
    file.write('</html>')

def send_email(subject, to, message):
    fromaddr = os.environ['REWE_GMAIL_SENDER']
    frompass = os.environ['REWE_GMAIL_PASS']

    msg = MIMEMultipart('alternative')
    msg['Subject'] = Header(subject, 'utf-8')
    msg['From'] = fromaddr
    msg['To'] = to

    msg.attach(MIMEText('Weekly Subreddit', 'plain'))
    msg.attach(MIMEText(message, 'html'))

    with smtplib.SMTP_SSL(host='smtp.gmail.com', port=465) as server:
        server.ehlo()
        server.login(fromaddr, frompass)
        server.sendmail(fromaddr, [to], msg.as_string())

def praw_instance(token):
    praw_inst = praw.Reddit(client_id=os.environ['REWE_REDDIT_APP_ID'],
                         client_secret=os.environ['REWE_REDDIT_APP_SECRET'],
                         username=os.environ['REWE_REDDIT_USERNAME'],
                         password=os.environ['REWE_REDDIT_PASSWORD'],
                         user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:52.0) Gecko/20100101 Firefox/52.0',
                         refresh_token=token)
    return praw_inst

def user_subreddits(reddit):
    return reddit.user.subreddits()

def send_newsletter(token, email):
    with io.StringIO() as body:
        file = weekly_page_header(body, css=REDDIT_CSS)
        praw_inst = praw_instance(token)

        for subreddit in user_subreddits(praw_inst):
            subreddit = subreddit.display_name
            weekly_page(praw_inst, subreddit, file)

        weekly_page_footer(file)
        email_body = Premailer(body.getvalue(),
                               base_url='https://www.reddit.com',
                               disable_leftover_css=True).transform()
        
        print("Sending weekly for {}...".format(email))
        send_email(subject='Reddit weekly',
                   to=email, message=email_body)

def main():
    send_newsletter(os.environ['REWE_REDDIT_REFRESH_TOKEN'], os.environ['REWE_DEST_EMAIL'])

# usage: ./rewe.py -u, --users=<json>

if __name__ == '__main__':
    if (len(sys.argv) > 1 and sys.argv[1] == '--force') or datetime.datetime.today().weekday() == 5:
        main()

