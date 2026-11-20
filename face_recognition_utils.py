import base64
import binascii
import io

import face_recognition
import numpy as np
from PIL import Image, UnidentifiedImageError


class FaceImageError(ValueError):
    pass


def decode_face_image(value):
    if not isinstance(value, str) or not value:
        raise FaceImageError("Capture or choose an image before continuing.")
    if value.startswith("data:"):
        header, separator, encoded = value.partition(",")
        if not separator or not header.lower().startswith("data:image/") or ";base64" not in header.lower():
            raise FaceImageError("The image must be a base64-encoded image.")
    else:
        encoded = value
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise FaceImageError("The image data is invalid. Capture or choose the image again.") from error
    if not image_bytes:
        raise FaceImageError("The selected image is empty.")
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"}:
                raise FaceImageError("Use a JPEG, PNG, or WebP image.")
            if image.width * image.height > 16_000_000:
                raise FaceImageError("The image dimensions are too large. Choose a smaller image.")
            image = image.convert("RGB")
            image.thumbnail((1600, 1600))
            return np.asarray(image)
    except Image.DecompressionBombError as error:
        raise FaceImageError("The image dimensions are too large. Choose a smaller image.") from error
    except (UnidentifiedImageError, OSError) as error:
        raise FaceImageError("That file is not a valid image.") from error


def encode_face(image):
    locations = face_recognition.face_locations(image, model="hog")
    if not locations:
        raise FaceImageError("No face was found. Face the camera and try again.")
    if len(locations) != 1:
        raise FaceImageError("Only one face should be visible in the image.")
    encodings = face_recognition.face_encodings(image, known_face_locations=locations)
    if not encodings:
        raise FaceImageError("The face could not be read clearly. Try again in better lighting.")
    return np.asarray(encodings[0], dtype=np.float64)


def find_match(encoding, students, threshold=0.48):
    match = find_match_with_distance(encoding, students, threshold=threshold)
    return (match[0], match[1]) if match else None


def find_match_with_distance(encoding, students, threshold=0.48):
    if not students:
        return None
    known_encodings = [student[2] for student in students]
    distances = face_recognition.face_distance(known_encodings, encoding)
    best_index = int(np.argmin(distances))
    if float(distances[best_index]) > threshold:
        return None
    # This is the model's Euclidean distance, not a probability or confidence percentage.
    return students[best_index][0], students[best_index][1], float(distances[best_index])
