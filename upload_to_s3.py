from __future__ import annotations
import os
import yaml
import base64
import aioboto3
from botocore.exceptions import EndpointConnectionError
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from logging import getLogger
import jwt
# from .models import prefix

prefix = ""

logger = getLogger("api")

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

def prepare_s3_config(config):
    try:
        s3_config = config.get("S3")
        s3_settings = {
            'S3_REGION_NAME': s3_config.get('REGION_NAME'),
            'S3_ACCESS_KEY': s3_config.get('ACCESS_KEY'),
            'S3_SECRET_KEY': s3_config.get('SECRET_KEY'),
            'ENDPOINT': s3_config.get('ENDPOINT')
        }
        bucket = None
        prefix = ""
        available_buckets = config.get("AVAILABLE_BUCKETS",[])
        for separate_bucket in available_buckets:
            if separate_bucket.get('type') == "configs" and separate_bucket.get('bucket'):
                bucket = separate_bucket['bucket']
                if separate_bucket.get('prefix'):
                    prefix = f"{separate_bucket['prefix']}/"

        s3_settings['bucket'] = bucket
        s3_settings['prefix'] = prefix
        return s3_settings
    except Exception as e:
        logger.error("Error occurred during prepare s3 config", exc_info=True)
        raise

def get_author(request):
    try:
        jwt_key = request.cookies.get("jwt")
        decoded = jwt.decode(jwt_key, options={"verify_signature": False})
        author = decoded.get("username")
    except:
        logger.warning("No JWT cookie or username found in the request. Using default user")
        author = "Default User"
    return author

class MethodUploadConfigPostRequest(BaseModel):
    folder: str = Field(..., description='ID of your CPE')
    filename: str = Field(..., description='Name of your new object')
    filecontent: str = Field(
        ..., description='Base64 string of an object you want to upload'
    )


@router.post('/method/UploadConfig', response_model=None,
             description="This method accepts a base64-encoded string and uploads it as a file to the storage. "
                         "The 'folder' and 'filename' fields are used to specify the full path to the file, while the"
                         " 'filecontent' field should contain the base64-encoded content "
                         "of the file you wish to upload. "
                         " \n"
                         " In order to use cURL commands insert your credentials (login, passwords) "
                         "into the cURL options as follows: ```  -u login:password  ```"
             )
async def post_method_upload_config(body: MethodUploadConfigPostRequest, request: Request):
    author = get_author(request)
    s3_settings = prepare_s3_config(config)
    folder = body.folder
    filename = body.filename
    s3_bucket_name = s3_settings.get('bucket')
    s3_path = s3_settings['prefix']
    fileid = f"{folder}/{filename}"
    filepath = f"{s3_path}{fileid}"
    session = aioboto3.Session()
    logger.info(f"Endpoint 'UploadConfig' initialized, folder={folder}, filepath={filepath}, author={author}")
    async with session.client('s3',
                              endpoint_url=s3_settings['ENDPOINT'],
                              region_name=s3_settings['S3_REGION_NAME'],
                              aws_access_key_id=s3_settings['S3_ACCESS_KEY'],
                              aws_secret_access_key=s3_settings['S3_SECRET_KEY']) as s3:
        what_to_decode = body.filecontent
        try:
            if "/" in folder or ".ignore" in folder:
                return JSONResponse(content={"result": {"code": 422,
                                                        "message": "Unprocessable Content",
                                                        "details": "Invalid folder name"}},
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
            logger.exception(f"Unable to get information from storage, prefix={s3_path}, object={filepath}")
            return JSONResponse(content={"result": {"code": 500,
                                                    "message": "Internal Server Error",
                                                    "details": "Could not connect to the config file storage"}},
                                status_code=500)
        except Exception as e:
            logger.exception(f"Error while decoding filecontent, filecontent={what_to_decode}", exc_info=e)
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
            logger.exception(f"Unable to get information from storage, prefix={s3_path}, object={filepath}")
            return JSONResponse(content={"result": {"code": 500,
                                                    "message": "Internal Server Error",
                                                    "details": "Could not connect to the config file storage"}},
                                status_code=500)
        except Exception as e:
            logger.exception(f"Error while uploading a file to {s3_bucket_name}{key}, file={image_data})", exc_info=e)
            return JSONResponse(content={"result": {"code": 500,
                                                    "message": "Internal Server Error",
                                                    "details": "Unable to upload a file"}},
                                status_code=500)

