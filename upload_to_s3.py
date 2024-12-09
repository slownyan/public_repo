from __future__ import annotations
import os
import yaml
import base64
import aioboto3
from botocore.exceptions import EndpointConnectionError
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from dmlog import get_logger
from .utils import prepare_s3_config, get_author
from .models import prefix
logger = get_logger("api")

with open(os.path.join(os.path.dirname(__file__), '../config.yml'), 'r') as configfile:
    config = yaml.safe_load(configfile)

router = APIRouter(
        prefix=prefix,
        responses={200: {"description": "OK"},
                   401: {"description": "Unauthorized"},
                   404: {"description": "Not found"},
                   422: {"description": "Unprocessable Content"},
                   500: {"description": "Internal server error"},
                   503: {"description": "Service Unavailable"}
                   },
        tags=['Configuration Files'],
)


class MethodUploadConfigPostRequest(BaseModel):
    cpe_id: str = Field(..., description='ID of your CPE')
    filename: str = Field(..., description='Name of your new object')
    filecontent: str = Field(
        ..., description='Base64 string of an object you want to upload'
    )


@router.post('/method/UploadConfig', response_model=None,
             description="This method accepts a base64-encoded string and uploads it as a file to the storage. "
                         "The 'cpe_id' and 'filename' fields are used to specify the full path to the file, while the"
                         " 'filecontent' field should contain the base64-encoded content "
                         "of the file you wish to upload. "
                         " \n"
                         " In order to use cURL commands insert your DMS credentials (login, passwords) "
                         "into the cURL options as follows: ```  -u login:password  ```"
             )
async def post_method_upload_config(body: MethodUploadConfigPostRequest, request: Request):
    author = get_author(request)
    s3_settings = prepare_s3_config(config)
    cpeid = body.cpe_id
    filename = body.filename
    s3_bucket_name = s3_settings.get('bucket')
    s3_path = s3_settings['prefix']
    fileid = f"{cpeid}/{filename}"
    filepath = f"{s3_path}{fileid}"
    session = aioboto3.Session()
    logger.info(f"Endpoint 'UploadConfig' initialized",
                cpeid=cpeid, filepath=filepath, author=author)
    async with session.client('s3',
                              endpoint_url=s3_settings['ENDPOINT'],
                              region_name=s3_settings['S3_REGION_NAME'],
                              aws_access_key_id=s3_settings['S3_ACCESS_KEY'],
                              aws_secret_access_key=s3_settings['S3_SECRET_KEY']) as s3:
        what_to_decode = body.filecontent
        try:
            if "/" in cpeid or ".ignore" in cpeid:
                return JSONResponse(content={"result": {"code": 422,
                                                        "message": "Unprocessable Content",
                                                        "details": "Invalid cpeid"}},
                                    status_code=200)
            else:
                pass
            if ".ignore" in filename:
                return JSONResponse(content={"result": {"code": 422,
                                                        "message": "Unprocessable Content",
                                                        "details": "Invalid filename"}},
                                    status_code=200)
            image_data = base64.b64decode(what_to_decode)
            key = filepath
        except EndpointConnectionError:
            logger.exception(f"Unable to get information from storage",
                             Prefix=s3_path, object=filepath)
            return JSONResponse(content={"result": {"code": 500,
                                                    "message": "Internal Server Error",
                                                    "details": "Could not connect to the config file storage"}},
                                status_code=500)
        except Exception as e:
            logger.exception(f"Error while decoding filecontent", filecontent=what_to_decode, exception=e)
            return JSONResponse(content={"result": {"code": 400,
                                                    "message": "Bad request",
                                                    "details": "Error while decoding filecontent"}},
                                status_code=200)

        try:
            await s3.put_object(Bucket=s3_bucket_name, Key=key, Body=image_data, ContentType='text/plain')
            logger.info(f"File successfully uploaded to {fileid}")
            return JSONResponse(content={"result": {"code": 200,
                                                    "message": "OK",
                                                    "details": f"File successfully uploaded to {fileid}"}},
                                status_code=200)
        except EndpointConnectionError:
            logger.exception(f"Unable to get information from storage",
                             Prefix=s3_path, object=filepath)
            return JSONResponse(content={"result": {"code": 500,
                                                    "message": "Internal Server Error",
                                                    "details": "Could not connect to the config file storage"}},
                                status_code=500)
        except Exception as e:
            logger.exception(f"Error while uploading a file to {s3_bucket_name}{key}", file=image_data,
                             exception=e)
            return JSONResponse(content={"result": {"code": 500,
                                                    "message": "Internal Server Error",
                                                    "details": "Unable to upload a file"}},
                                status_code=500)

