#!/usr/bin/env python

# Orthanc - A Lightweight, RESTful DICOM Store
# Copyright (C) 2012-2016 Sebastien Jodogne, Medical Physics
# Department, University Hospital of Liege, Belgium
# Copyright (C) 2017-2022 Osimis S.A., Belgium
# Copyright (C) 2021-2022 Sebastien Jodogne, ICTEAM UCLouvain, Belgium
#
# This program is free software: you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.


import argparse
import bz2
import datetime
import gzip
import json
import os
import random
import uuid

import requests
import sys
import tarfile
import zipfile
from pydicom import dcmread
from io import BytesIO


parser = argparse.ArgumentParser(
    description='Command-line tool to import files or archives into Orthanc.'
)
parser.add_argument(
    '--url',
    default='http://localhost:8042',
    help='URL to the REST API of the Orthanc server'
)
parser.add_argument(
    '--force',
    help='Do not warn the user about deletion',
    action='store_true'
)
parser.add_argument(
    '--clear', help='Remove the content of the Orthanc database',
    action='store_true'
)
parser.add_argument(
    '--verbose',
    help='Be verbose',
    action='store_true')
parser.add_argument(
    '--ignore-errors',
    help='Do not stop if encountering non-DICOM files',
    action='store_true')
parser.add_argument(
    'files',
    metavar='N',
    nargs='*',
    help='Files to import'
)

args = parser.parse_args()


IMPORTED_STUDIES = set()
COUNT_ERROR = 0
COUNT_DICOM = 0
COUNT_JSON = 0


REQUIRED_TAGS_DEFAULT_VALUES = {
    'PatientID': '0',
    'SOPInstanceUID': '0',
    'SeriesInstanceUID':  '0',
    'StudyInstanceUID': '0'
}


def is_json(content):
    try:
        if sys.version_info >= (3, 0):
            json.loads(content.decode())
            return True
        else:
            json.loads(content)
            return True
    except:
        return False


def validate_dicom_tags(file_path):
    ds = dcmread(file_path)
    for keyword, value in REQUIRED_TAGS_DEFAULT_VALUES.items():
        if keyword not in ds:
            setattr(ds, keyword, value)
    out = BytesIO()
    ds.save_as(out)
    out.seek(0)
    return out.read()


def upload_buffer(dicom):
    global IMPORTED_STUDIES
    global COUNT_ERROR
    global COUNT_DICOM
    global COUNT_JSON

    if is_json(dicom):
        COUNT_JSON += 1
        return

    headers = {'content-type': 'application/dicom'}
    response = requests.post(
        url=f'{args.url}/instances',
        headers=headers,
        data=dicom
    )

    try:
        response.raise_for_status()
    except Exception as e:
        COUNT_ERROR += 1
        if args.ignore_errors:
            if args.verbose:
                print('  not a valid DICOM file, ignoring it')
            return
        else:
            print(f"There was an error uploading DICOM: {response.json()}")
            return

    info = response.json()
    COUNT_DICOM += 1

    if (isinstance(info, dict) and
            not info['ParentStudy'] in IMPORTED_STUDIES):
        IMPORTED_STUDIES.add(info['ParentStudy'])

        response_2 = requests.get(
            url=f'{args.url}/instances/{info["ID"]}/tags?short',
        )
        response_2.raise_for_status()
        tags = response_2.json()

        print('')
        print('New imported study:')
        print('  Orthanc ID of the patient: %s' % info['ParentPatient'])
        print('  Orthanc ID of the study: %s' % info['ParentStudy'])
        print('  DICOM Patient ID: %s' % (
            tags['0010,0020'] if '0010,0020' in tags else '(empty)'))
        print('  DICOM Study Instance UID: %s' % (
            tags['0020,000d'] if '0020,000d' in tags else '(empty)'))
        print('')


def upload_file(file_path):
    dicom = validate_dicom_tags(file_path)
    if args.verbose:
        print('Uploading: %s (%dMB)' % (file_path, len(dicom) / (1024 * 1024)))

    upload_buffer(dicom)


def upload_bzip2(file_path):
    with bz2.BZ2File(file_path, 'rb') as f:
        dicom = validate_dicom_tags(file_path)
        if args.verbose:
            print('Uploading: %s (%dMB)' % (file_path, len(dicom) / (1024 * 1024)))

        upload_buffer(dicom)


def upload_gzip(file_path):
    with gzip.open(file_path, 'rb') as f:
        dicom = validate_dicom_tags(file_path)
        if args.verbose:
            print('Uploading: %s (%dMB)' % (file_path, len(dicom) / (1024 * 1024)))

        upload_buffer(dicom)


def upload_tar(file_path, decoder):
    if args.verbose:
        print(f'Uncompressing tar archive: {file_path}')
    with tarfile.open(file_path, decoder) as tar:
        for item in tar:
            if item.isreg():
                f = tar.extractfile(item)
                dicom = f.read()
                f.close()

                if args.verbose:
                    print(f'Uploading: {item.name} ({len(dicom) / (1024 * 1024)}MB)')

                upload_buffer(dicom)


def upload_zip(file_path):
    if args.verbose:
        print('Uncompressing ZIP archive: %s' % file_path)
    with zipfile.ZipFile(file_path, 'r') as zip:
        for item in zip.infolist():
            # WARNING - "item.is_dir()" would be better, but is not available in Python 2.7
            if item.file_size > 0:
                dicom = zip.read(item.filename)

                if args.verbose:
                    print('Uploading: %s (%dMB)' % (item.filename, len(dicom) / (1024 * 1024)))

                upload_buffer(dicom)


def decode_file(file_path):
    extension = os.path.splitext(file_path)[1]

    if file_path.endswith('.tar.bz2'):
        upload_tar(file_path, 'r:bz2')
    elif file_path.endswith('.tar.gz'):
        upload_tar(file_path, 'r:gz')
    elif extension == '.zip':
        upload_zip(file_path)
    elif extension == '.tar':
        upload_tar(file_path, 'r')
    elif extension == '.bz2':
        upload_bzip2(file_path)
    elif extension == '.gz':
        upload_gzip(file_path)
    else:
        upload_file(file_path)


if args.clear:
    print('Removing the content of Orthanc')

    r = requests.get(f'{args.url}/studies')
    r.raise_for_status()

    print('  %d studies are being removed...' % len(r.json()))

    for study in r.json():
        requests.delete('%s/studies/%s' % (args.url, study)).raise_for_status()

    print('Orthanc is now empty')
    print('')

for path in args.files:
    if os.path.isfile(path):
        decode_file(path)
    elif os.path.isdir(path):
        for root, dirs, files in os.walk(path):
            for name in files:
                decode_file(os.path.join(root, name))
    else:
        raise Exception('Missing file or directory: %s' % path)

print('')

if COUNT_ERROR == 0:
    print('SUCCESS:')
else:
    print('WARNING:')

print('  %d DICOM instances properly imported' % COUNT_DICOM)
print('  %d DICOM studies properly imported' % len(IMPORTED_STUDIES))
print('  %d JSON files ignored' % COUNT_JSON)
print('  Error in %d files' % COUNT_ERROR)
print('')
