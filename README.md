This is a Showcase project for creating a DICOM viewer and server to be able to view and annotate DICOM files


For the DICOM viewer we are using OHIF

For the DICOM server we are using Orthanc

The connection between the server and the client is configured using an Ngnix Proxy

to run:
```shell
docker compose pull
docker compose up -d
```

once the server is up and running, to load the dicom files run:
```shell
pip3 install -r requirements.txt
python3 upload_dicom_files.py --url http://localhost:3337 --clear
python3 upload_dicom_files.py --url http://localhost:3337 <dicom_dir_path>
```

Then in the browser go to `http://localhost:8888` to see the OHIF viewer

To view the files in the server, go to `http://localhost:3337/app/explorer.html`
