# Built-In Imports
import logging.config
import os
import time
from typing import Union

# External Imports
import cv2
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from starlette.responses import ContentStream
import uvicorn

# Getting the current/root File's location.
ROOT_FILE: str = os.path.abspath(__file__)

# Getting the current/root directory
ROOT_DIRECTORY: str = os.path.dirname(ROOT_FILE)

BACKEND_LOGGER: logging.Logger = logging.getLogger("BACKEND_LOGGER")
# Set the logging level
BACKEND_LOGGER.setLevel(logging.DEBUG)

# Create a console handler
CONSOLE_HANDLER = logging.StreamHandler()
# Set the logging level for the handler
CONSOLE_HANDLER.setLevel(logging.DEBUG)

# Create a formatter and attach it to the handler
FORMATTER = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
CONSOLE_HANDLER.setFormatter(FORMATTER)

# Add the handler to the logger
BACKEND_LOGGER.addHandler(CONSOLE_HANDLER)

APP: FastAPI = FastAPI()


@APP.get("/")
async def root() -> dict:
    """Returns a greeting message.

    Returns:
        dict: A dictionary containing a greeting message.

    Notes:
        This is the root endpoint of the application.
    """
    return {"message": "Hello World"}


KVM_NOT_CONNECTED_FILE_PATH: str = os.path.join(ROOT_DIRECTORY,
                                                "assets",
                                                "kvm_not_connected.jpg")

with open(KVM_NOT_CONNECTED_FILE_PATH, "rb") as file_object:
    KVM_NOT_CONNECTED_IMAGE: bytes = file_object.read()


def read_kvm_video_frames(video_interface: cv2.VideoCapture) -> ContentStream:
    """Reads frames from a kvm video interface and yield them as JPEG bytes.

    This function continuously reads frames from the specified kvm video
    interface, converts them to JPEG format, and yields them as bytes.
    The generator runs indefinitely until an exception occurs or if the client
    has disconnected.

    Args:
        video_interface (cv2.VideoCapture): The opencv video interface to the connected device.

    Yields:
        bytes: Frame data in multipart MIME format with JPEG content type.
    """
    frame_count = 0

    # Start time for calculating FPS
    start_time = time.time()

    try:
        # Loop until the client connection exist
        while True:
            # Check if the camera capture is successfully opened
            if not video_interface.isOpened():
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' +
                       KVM_NOT_CONNECTED_IMAGE + b'\r\n')
                yield b'--frame--\r\n'
                BACKEND_LOGGER.info("The kvm interface is not opening, closing the stream.")
                break

            # Read a frame from the kvm video object
            read_status, frame = video_interface.read()

            if not read_status:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' +
                       KVM_NOT_CONNECTED_IMAGE + b'\r\n')
                yield b'--frame--\r\n'
                BACKEND_LOGGER.info("Failed to read new kvm frame, closing the stream.")
                break
            else:
                # Convert frame to JPEG format
                _, encoded_image = cv2.imencode(".jpeg", frame)

                image_bytes = encoded_image.tobytes()

                # Yield the frame data as multipart MIME with JPEG content type
                yield b"--frame\r\n" b"Content-Type: image/jpeg\r\n\r\n" + image_bytes + b"\r\n"

            frame_count += 1

            # Check if one second has elapsed
            if time.time() - start_time > 1:
                # Calculate the current FPS
                fps = frame_count / (time.time() - start_time)

                BACKEND_LOGGER.info(f"KVM FPS: {int(fps)}.")

                # Reset the frames count to zero
                frame_count = 0

                # Reset the start time to the current time
                start_time = time.time()
    except GeneratorExit:
        BACKEND_LOGGER.error("Exiting the generator for kvm.")
    except Exception:
        BACKEND_LOGGER.error("Exiting the function for kvm due to general exception.")
    finally:
        BACKEND_LOGGER.info("Closing the SSE connection.")
        BACKEND_LOGGER.info(f"Releasing the KVM for the client.")

        video_interface.release()


@APP.get("/kvm-stream/", response_model=None)
async def open_kvm_stream() -> Union[StreamingResponse, FileResponse]:
    """Open a KVM streaming endpoint to capture frames from the connected device.

    This endpoint uses FastAPI's StreamingResponse to continuously
    stream frames captured from the open cv interface. The frames
    are sent with the specified media type "multipart/x-mixed-replace;
    boundary=frame".

    Returns:
        Union[StreamingResponse, FileResponse]: Either a StreamingResponse that
        continuously streams frames from the kvm display or a FileResponse
        with a jpeg image as fallback.
    """
    video_index: int = 0
    backend_api: int = cv2.CAP_MSMF
    video_interface: cv2.VideoCapture = cv2.VideoCapture(video_index, backend_api)
    video_interface.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    video_interface.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    video_interface.set(cv2.CAP_PROP_FPS, 30)

    try:
        # Read a frame from the kvm video object
        read_status, frame = video_interface.read()

        if not read_status:
            return FileResponse(
                KVM_NOT_CONNECTED_FILE_PATH,
                media_type="image/jpeg")

    except Exception:
        return FileResponse(
            KVM_NOT_CONNECTED_FILE_PATH,
            media_type="image/jpeg")

    try:
        # Return a StreamingResponse that continuously streams frames
        return StreamingResponse(
            read_kvm_video_frames(video_interface),
            media_type="multipart/x-mixed-replace;boundary=frame"
        )

    # If an exception occurs (e.g., video capture error)
    # Return an jpeg image response
    except Exception:
        return FileResponse(KVM_NOT_CONNECTED_FILE_PATH, media_type="image/jpeg")

@APP.websocket("/websocket/kvm-stream")
async def stream_kvm(websocket: WebSocket) -> Optional[bytes]:
    """KVM streamer with h264 encoding.

    This function will create an FFMPEG pipeline to read kvm frame from the usb, encode it
    to h264 annexure b format, and read the output bytes using subprocess pipe
    and parse them to create individual nal data and sends them to the client.

    Args:
        websocket (WebSocket): The WebSocket object to establish the connection.

    Returns:
        Optional[bytes]: The encoded video data.
    """
    await websocket.accept()

    kvm_device_name = "video_capture_device"

    if not kvm_device_name:
        BACKEND_LOGGER.error("KVM not found, closing the connection.")
        await websocket.close()
        return

    ffmpeg_executable_location = os.path.join("D:", "my_software",
                                              "ffmpeg", "ffmpeg-static-win64-gpl",
                                              "bin", "ffmpeg.exe")

    ffmpeg_command = [
        ffmpeg_executable_location,
        '-f', 'dshow',
        '-i', 'video=' + kvm_device_name,
        '-s', '1920x1080',
        '-c:v', 'libx264',
        '-preset', 'ultrafast',
        '-tune', 'zerolatency',
        '-profile:v', 'high',
        '-level', '4',
        '-pix_fmt', 'yuv420p',
        '-f', 'h264',
        '-'
    ]

    # Start the FFMPEG process.
    try:
        encoder_process_interface = await asyncio.create_subprocess_exec(
            *ffmpeg_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0)
    except FileNotFoundError:
        BACKEND_LOGGER.error(f"The FFMPEG executable is not"
                             f" found at: {ffmpeg_executable_location}")
        BACKEND_LOGGER.error("Exiting the KVM stream process.")
        await websocket.close()
        return
    except Exception as error:
        BACKEND_LOGGER.error(f"An unexpected error occurred: {error}")
        BACKEND_LOGGER.error("Exiting the KVM stream process.")
        await websocket.close()
        return

    BACKEND_LOGGER.info(f"FFMPEG Process to Encode KVM stream has been "
                        f"started with process id: {encoder_process_interface.pid}")

    complete_frame_data: bytes = b""

    # Define the regex pattern.
    nal_start_code_pattern: Pattern[bytes] = re.compile(b'(?:\x00\x00\x00\x01)')

    while True:
        try:
            # Read 300 KB (307200 bytes) of data, this will read at most 300KB, if less data
            # is available it will return only those available data, and will not wait
            # for complete 300KB. This number is based on trail and error
            # the maximum IDR frame size was around 280KB.
            new_encoded_data: bytes = await encoder_process_interface.stdout.read(307200)
        except Exception as error:
            BACKEND_LOGGER.error("Error while reading from FFMPEG process pipeline.")
            BACKEND_LOGGER.error(error)
            BACKEND_LOGGER.error("Exiting from the KVM Stream.")
            break

        if not new_encoded_data:
            BACKEND_LOGGER.error("There is no data from FFMPEG process, exiting the stream.")
            break

        # Find all non-overlapping matches.
        nal_matches_info: list = list(nal_start_code_pattern.finditer(new_encoded_data))

        no_of_nal_units: int = len(nal_matches_info)

        # If there were no matches, it means the current chunk of data has intermediary
        # Bytes which continues from previous data, hence they should simply be added to the
        # Existing nal data and skip the remaining code.
        if not nal_matches_info:
            complete_frame_data += new_encoded_data
            continue

        for match_index, match in enumerate(nal_matches_info):
            nal_type: int = new_encoded_data[match.end()] & 0x1F

            # If the first match in the list of matches occurs somewhere not in the first index
            # Then first few bytes (before the start index of the first match) would correspond
            # To the data from the previous nal unit, hence we need to add them to the
            # Existing nal data and then send to the client and then clear the buffer.
            if match_index == 0 and match.start() != 0:
                complete_frame_data += new_encoded_data[: match.start()]

            if complete_frame_data:
                # We send only if the current nal is Non-Idr, since other data such as SPS, PPS,
                # SEI, IDR would actually come as separate chunks, we need to combine them before
                # sending. The implementation takes care of combining them, but happens only if a
                # Non-Idr frame comes After the Key Frame (which is a combination of SPS, PPS,
                # SEI, IDR).
                if nal_type == 1:
                    try:
                        await websocket.send_bytes(complete_frame_data)
                    except WebSocketDisconnect:
                        BACKEND_LOGGER.error("The Client has disconnected,"
                                             " exiting from the KVM stream.")
                        BACKEND_LOGGER.info("Closing the websocket connection.")
                        await websocket.close()
                        BACKEND_LOGGER.info("closed.")
                        BACKEND_LOGGER.info("Terminating the FFMPEG process pipeline.")
                        try:
                            encoder_process_interface.terminate()
                            BACKEND_LOGGER.info("Terminated.")
                        except Exception:
                            BACKEND_LOGGER.warning("Couldn't terminate the process.")
                        return
                    except Exception as error:
                        BACKEND_LOGGER.error("Error while sending data to the client.")
                        BACKEND_LOGGER.error(error)
                        BACKEND_LOGGER.error("Exiting from the KVM Stream.")
                        BACKEND_LOGGER.info("Closing the websocket connection.")
                        await websocket.close()
                        BACKEND_LOGGER.info("closed.")
                        BACKEND_LOGGER.info("Terminating the FFMPEG process pipeline.")
                        try:
                            encoder_process_interface.terminate()
                            BACKEND_LOGGER.info("Terminated.")
                        except Exception:
                            BACKEND_LOGGER.warning("Couldn't terminate the process.")
                        return

                    # Yield control back to the event loop to prevent buffer overflow and ensure
                    # consistent frame rate.
                    #
                    # This line addresses two key issues:
                    # 1. Frame rate regulation: Without this, the client receives frames
                    # at an excessively high rate (> 3000 FPS).
                    # 2. Encoder output buffer management: FFMPEG requires periodic buffer
                    # clearance to output data. If the event loop is not yielded, the buffer
                    # will not be cleared, causing the code to hang
                    # at `await encoder_process_interface.stdout.read(307200)`.
                    await asyncio.sleep(0)
                    complete_frame_data = b''

            # If this is the last item in the list of matches, then we add all the data
            # From the start of its index till the end.
            if match_index == no_of_nal_units - 1:
                complete_frame_data += new_encoded_data[match.start():]
            else:
                # If this is not the last item in the list of matches, then we add all the data
                # From the start of the index, till (but not including) the start of the next
                # Match.
                next_nal_index = match_index + 1
                next_nal_start = nal_matches_info[next_nal_index].start()
                complete_frame_data += new_encoded_data[match.start():next_nal_start]

    BACKEND_LOGGER.info("Closing the websocket connection.")
    await websocket.close()
    BACKEND_LOGGER.info("closed.")
    BACKEND_LOGGER.info("Terminating the FFMPEG process pipeline.")
    try:
        encoder_process_interface.terminate()
        BACKEND_LOGGER.info("Terminated.")
    except Exception:
        BACKEND_LOGGER.warning("Couldn't terminate the process.")


if __name__ == "__main__":
    config = uvicorn.Config(app=APP, host="0.0.0.0", port=5566, log_level="info")

    server = uvicorn.Server(config)
    server.run()