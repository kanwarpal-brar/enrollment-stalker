import argparse
import smtplib
import ssl
import time
from typing import Callable, Any
from email.message import EmailMessage
import json
import os
from dotenv import load_dotenv

import pandas
import requests

load_dotenv()

POLLING_INTERVAL_SEC = int(os.getenv('POLLING_INTERVAL_SEC', 3))
MAIL_PORT = int(os.getenv('MAIL_PORT', 465))  # For SSL
MAIL_PASS = os.getenv('MAIL_PASS')
MAIL_NAME = os.getenv('MAIL_NAME')
TARGET_MAIL_NAME = os.getenv('TARGET_MAIL_NAME')
KEY = os.getenv('API_KEY')

def send_alert_mail(body: str, subject: str):
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", MAIL_PORT, context=context) as server:
        server.login(MAIL_NAME, MAIL_PASS)
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = MAIL_NAME
        msg['To'] = TARGET_MAIL_NAME
        msg.set_content(body)
        server.send_message(msg)


def get_class_data(url: str, headers, classNumber: int = None) -> requests.Response.content:
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        data = json.loads(res.content)
        for item in data:
            if item["courseComponent"] == "LEC" and (classNumber is None or item["classNumber"] == classNumber):
                return item
        return data
    raise Exception(f'HTTP Request Error, code {res.status_code}, content:\n {res.content}')


def scrape_class_data(url: str, query_str: str) -> requests.Response.content:
    res = requests.post(url, data=query_str)
    if res.status_code == 200:
        return res.content
    raise Exception(f'Request Error, code ${res.status_code}, content:\n ${res.content}')


def check_status(html_str: str, func: Callable[[Any], bool]) -> bool:
    table = pandas.read_html(html_str)[1]
    return func(table)


def polling_manager(url: str, head, df_func):
    print("Poll Starting")
    was_active = False
    while True:
        data = get_class_data(url, head, TARGET_CLASS_NUMBER)
        status = df_func(data)
        if status and not was_active:
            was_active = True
            send_alert_mail("CLASS IS OPEN",
                            f"{TARGET_COURSE_SUBJECT} {TARGET_COURSE_CODE} IS OPEN")
        elif was_active and not status:
            send_alert_mail("CLASS CLOSED AGAIN",
                            f"{TARGET_COURSE_SUBJECT} {TARGET_COURSE_CODE} CLOSED AGAIN")
            was_active = False

        time.sleep(POLLING_INTERVAL_SEC)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Monitor class enrollment status.')
    parser.add_argument('term_code', type=str, help='Term code (e.g. 1241 for Winter 2024)')
    parser.add_argument('course_subject', type=str, help='Course subject code (e.g. CS, MATH)')
    parser.add_argument('course_code', type=str, help='Course number (e.g. 135, 146)')
    parser.add_argument('class_number', type=int, help='Class number from schedule')

    args = parser.parse_args()

    TARGET_TERM_CODE = str(args.term_code)
    TARGET_COURSE_SUBJECT = str(args.course_subject)
    TARGET_COURSE_CODE = str(args.course_code)
    TARGET_CLASS_NUMBER = int(args.class_number)

    target_url = "https://classes.uwaterloo.ca/cgi-bin/cgiwrap/infocour/salook.pl"
    target_query_str = f"level=under&sess=1239&subject={TARGET_COURSE_SUBJECT}&cournum={TARGET_COURSE_CODE}"
    target_schedules_url = (f"https://openapi.data.uwaterloo.ca/v3/ClassSchedules/"
                            f"{TARGET_TERM_CODE}/{TARGET_COURSE_SUBJECT}/{TARGET_COURSE_CODE}")
    header = {"x-api-key": KEY}

    def check_func_http(data) -> bool:
        try:
            return data["enrolledStudents"] < data["maxEnrollmentCapacity"]
        except Exception as e:
            print(e, data)


    send_alert_mail("STARTING MONITOR", "STARTING MONITOR")
    polling_manager(target_schedules_url, header, check_func_http)
