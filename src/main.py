from fastapi import FastAPI, Query, UploadFile, File
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.params import Query
import numpy as np
import nibabel as nib
from pathlib import Path
from tempfile import NamedTemporaryFile
import cv2
import shutil
import tensorflow as tf
import datetime
import enum
import sys
from pathlib import Path
sys.path.insert(1, str((Path(__file__).parent / '../src').resolve()))
from images2frames import resize_to_input_shape, normalize

model = tf.keras.models.load_model('data/model/memento.h5')


class PredictionFormatEnum(str, enum.Enum):
    TXT = "txt"
    JSON = "json"


class ReportFormatEnum(str, enum.Enum):
    TXT = "txt"
    JSON = "json"
    HTML = "html"


def classify(image):
    return list(map(float, model.predict(image)))


def save_upload_file_tmp(upload_file: UploadFile) -> Path:
    try:
        suffix = Path(upload_file.filename).suffix
        with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(upload_file.file, tmp)
            tmp_path = Path(tmp.name)
    finally:
        upload_file.file.close()
    return tmp_path


app = FastAPI()


@app.post("/predict")
def predict(
    image: UploadFile = File(...),
    format: PredictionFormatEnum = Query(
        "json",
        description="The format in which the output will be returned",
    )
):
    tmp_path = save_upload_file_tmp(image)
    try:
        res = {
            "probability": classify(np.expand_dims(cv2.imread(str(tmp_path), cv2.IMREAD_GRAYSCALE), 0))[0]
        }
    finally:
        tmp_path.unlink()
    return res if format == "json" else res["probability"]


@app.post("/report")
def report(
    scan: UploadFile = File(...),
    format: ReportFormatEnum = Query(
        "json",
        description="The format in which the output will be returned",
    )
):
    tmp_path = save_upload_file_tmp(scan)
    try:
        image = nib.load(tmp_path).get_fdata()
        if len(image.shape) == 4:
            image = np.mean(image, axis=3)
        image = normalize(image)
        image = resize_to_input_shape(image, n_frames=20)
        res = {
            "probabilities": classify(np.vstack([np.expand_dims(image[:, :, i], 0) for i in range(20)])),
        }
        res["final_probability"] = np.mean(res["probabilities"])

        if format == "txt":
            with open(Path(__file__).parent / "resources/templates/report.txt") as f:
                template = f.read()
            res = PlainTextResponse(template.format(
                str(datetime.datetime.now(datetime.timezone.utc)).center(60),
                scan.filename,
                *list(map(lambda x: f"{round(x*100, 2)}%".center(10), res["probabilities"])),
                f"{round(res['final_probability'] * 100, 2)}%".center(60)
            ), media_type="text/plain; charset=utf-8")
        elif format == "html":
            with open(Path(__file__).parent / "resources/templates/report.html") as f:
                template = f.read()
            res = HTMLResponse(template.format(
                str(datetime.datetime.now(datetime.timezone.utc)).center(60),
                scan.filename,
                *list(map(lambda x: f"{round(x*100, 2)}%".center(10), res["probabilities"])),
                f"{round(res['final_probability'] * 100, 2)}%".center(60)
            ))
    finally:
        tmp_path.unlink()

    return res


@app.get("/")
def root():
    return {"status": "ok"}
