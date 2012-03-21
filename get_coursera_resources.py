#! /usr/bin/env python
from __future__ import print_function
from lxml import etree
import mechanize
import argparse
import platform
import getpass
import string
import sys
import os
import re

RESOURCE_DICTS = [{'arg': 'pdfs',  'extension': 'pdf'},
                  {'arg': 'pptx',  'extension': 'pptx'},
                  {'arg': 'subs',  'extension': 'srt'},
                  {'arg': 'video', 'extension': 'mp4'}]

WIN_VALID_CHARS = '-_.() ' + string.ascii_letters + string.digits
MAX_WIN_FILE_SIZE = 50
MAX_LINUX_FILE_SIZE = 140
IS_WINDOWS = platform.system() == 'Windows'

def make_valid_filename(filename):
    if IS_WINDOWS:
        return ''.join((c if c in WIN_VALID_CHARS else '_') for c in filename)[:MAX_WIN_FILE_SIZE]
    else:
        return filename.replace(os.sep, '_')[:MAX_LINUX_FILE_SIZE]

# Based in PabloG answer at http://stackoverflow.com/questions/22676/how-do-i-download-a-file-over-http-using-python
def download_to_file(open_url, file_name):
    with open(file_name, 'wb') as f:
        meta = open_url.info()
        length_headers = meta.getheaders('Content-Length')
        file_size = int(length_headers[0]) if length_headers else None
        print('Downloading: {0}'.format(file_name))

        file_size_dl = 0
        block_sz = 8192
        while True:
            buf = open_url.read(block_sz)
            if not buf:
                break

            file_size_dl += len(buf)
            f.write(buf)
            fsdmb = '{0:d}'.format(file_size_dl / 1000000)
            fsdkb = '{0:03d}'.format(file_size_dl / 1000 % 1000)
            fsd = '{0}.{1}'.format(fsdmb, fsdkb)
            if file_size:
                fsmb = '{0:d}'.format(file_size / 1000000)
                fskb = '{0:03d}'.format(file_size / 1000 % 1000)
                fs = '{0}.{1}'.format(fsmb, fskb)
                percentage = '{0:.2f}'.format(file_size_dl * 100. / file_size)
                status = r'{0:>8s}/{1:s} Mb [{2}%]'.format(fsd, fs, percentage)
            else:
                status = r'{0:>8s} Mb'.format(fsd)
            status = status + chr(8) * (len(status) + 1)
            print(status, end='')


def clean_lecture_name(lecture_name):
    if '(' in lecture_name:
        lecture_name = lecture_name.rpartition('(')[0]
    return lecture_name.strip()

WEEK_RE = re.compile(r'(.*)\(week (\d+)\)$')
def take_week_from_section(section):
    week = 0
    match = WEEK_RE.match(section)
    if match:
        section, week = match.groups()
        section = section.strip()
        week = int(week)
    return section, week

def compare_sections(s1, s2):
    if (s1[1] != s2[1]):
        return s1[1] - s2[1]
    if (s1[2] != s2[2]):
        return s1[1] - s2[1]
    assert False


def main():
    parser = argparse.ArgumentParser(description='Gets lecture resources (videos by default) of an online Coursera course.')
    parser.add_argument('course_id', help='Course identifier (found in URL after www.coursera.org)')
    parser.add_argument('email', help='Your coursera email.')
    parser.add_argument('password', nargs='?', default=None, help='Your coursera password. You can omit it in the command line and provide it interactively.')
    parser.add_argument('--pdfs', action='store_true', help='Get the pdfs for each lecture. Disabled by default.')
    parser.add_argument('--pptx', action='store_true', help='Get the pptx\'s for each lecture. Disabled by default.')
    parser.add_argument('--subs', action='store_true', help='Get the subtitles for each lecture. Disabled by default.')
    parser.add_argument('--no-video', dest='video', action='store_false', help='Do not download the videos. Use this if you only want other resources such as pdfs.')
    parser.add_argument('--section-lecture-format', dest='section_lecture_format', action='store_true', help='Use the section number on the name of lectures. Ex: file abc which belongs to the first lecture of section 2 will get named 2.1 - abc')
    args = parser.parse_args()

    if not any(getattr(args, res_dict['arg']) for res_dict in RESOURCE_DICTS):
        print('ERROR: You disabled video download but didn\'t enable any other resource for download.')
        sys.exit()

    if not args.password:
        args.password = getpass.getpass('Coursera password: ')


    course_url = 'https://www.coursera.org/{0}/lecture/index'.format(args.course_id)

    print('Authenticating')
    browser = mechanize.Browser()
    browser.set_handle_robots(False)
    ## auth for one, auth for all (i.e. crypto doesn't matter)
    auth_url = 'https://www.coursera.org/crypto/auth/auth_redirector?type=login&subtype=normal&email=&minimal=true'
    browser.open(auth_url)
    ## unnamed form
    browser.select_form(nr=0)
    browser['email'] = args.email
    browser['password'] = args.password
    browser.submit()
    if 'Login Failed' in browser.title():
        print('ERROR: Authentication failed, please check your email and password.')
        sys.exit()
    print('Authentication successful')

    print('Trying to open lecture index page')
    try:
        doc = browser.open(course_url).read()
    except mechanize.HTTPError:
        print('ERROR: Failed to open lecture index page at {0}'.format(course_url))
        print('Please make sure the course identifier you provided ({0}) is correct.'.format(args.course_id))
        sys.exit()

    print('Done')
    tree = etree.HTML(doc)
    course_title = tree.xpath('//div[@id="course-logo-text"]/a/img/@alt')[0].strip()
    course_title = make_valid_filename(course_title)

    item_list = tree.xpath('//div[@class="item_list"]')[0]
    print('Starting downloads')
    sections = []
    for i in xrange(0, len(item_list)/2):
        section_el, lecture_list_el = item_list[2*i], item_list[2*i+1]
        section = section_el.xpath('./h3/text()')[0].strip()
        no_week_section, week = take_week_from_section(section)
        sections.append((no_week_section, week, i, lecture_list_el))
    sections = sorted(sections, compare_sections)

    for i, (no_week_section, week, _, lecture_list_el) in enumerate(sections, 1):
        section = '{0} - {1}'.format(i, no_week_section)
        if week:
            section += ' (week {0})'.format(week)
        section = make_valid_filename(section)
        section_folder = os.path.join(course_title, section)
        if not os.path.exists(section_folder):
            os.makedirs(section_folder)
        lecture_names = lecture_list_el.xpath('./li/a/text()')
        final_lecture_names = []
        for j, lecture_name in enumerate(lecture_names, 1):
            lecture_name = clean_lecture_name(lecture_name)
            lecture_name = '{0} - {1}'.format(j, lecture_name)
            if args.section_lecture_format:
                lecture_name = '{0}.{1}'.format(i, lecture_name)
            lecture_name = make_valid_filename(lecture_name)
            lecture_name = os.path.join(section_folder, lecture_name)
            final_lecture_names.append(lecture_name)
        url_list = lecture_list_el.xpath('./li/div[@class="item_resource"]/a/@href')
        for j, url in enumerate(url_list):
            resource_dict = RESOURCE_DICTS[j%4]
            if getattr(args, resource_dict['arg']):
                file_name = final_lecture_names[j/4]
                full_file_name = '{0}.{1}'.format(file_name, resource_dict['extension'])
                if not os.path.exists(full_file_name):
                    open_url = browser.open(url)
                    download_to_file(open_url, full_file_name)
    print('All requested resources have been downloaded')

if __name__ == '__main__':
    main()
