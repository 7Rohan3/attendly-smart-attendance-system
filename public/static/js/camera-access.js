(() => {
  function cameraError(error) {
    if (error.name === "NotAllowedError" || error.name === "PermissionDeniedError") {
      return "Camera permission was blocked. Allow camera access for this localhost site in your browser settings, then try again.";
    }
    if (error.name === "NotFoundError" || error.name === "DevicesNotFoundError") {
      return "No camera was found. Connect or enable a camera, or choose a photo instead.";
    }
    if (error.name === "NotReadableError" || error.name === "TrackStartError") {
      return "The camera is busy or unavailable. Close other apps using it, then try again.";
    }
    if (error.name === "SecurityError") {
      return "Camera access requires localhost or a secure HTTPS connection.";
    }
    if (error.message && error.message.includes("timed out")) {
      return "The camera opened but did not start sending video. Close other camera apps and retry.";
    }
    return "Could not start the camera. Check your camera settings and try again.";
  }

  function createCameraController(video, picker, onError) {
    const pickerLabel = picker.closest(".camera-picker");
    let stream;
    let devices = [];

    async function enumerateCameras() {
      if (!navigator.mediaDevices?.enumerateDevices) return;
      const currentDevice = stream?.getVideoTracks()[0]?.getSettings().deviceId;
      devices = (await navigator.mediaDevices.enumerateDevices())
        .filter((device) => device.kind === "videoinput");
      picker.replaceChildren();
      devices.forEach((device, index) => {
        const option = document.createElement("option");
        option.value = device.deviceId;
        option.textContent = device.label || `Camera ${index + 1}`;
        picker.append(option);
      });
      pickerLabel.hidden = devices.length < 2;
      if (currentDevice && devices.some((device) => device.deviceId === currentDevice)) {
        picker.value = currentDevice;
      }
    }

    async function requestCamera(deviceId) {
      const videoConstraints = deviceId
        ? { deviceId: { exact: deviceId }, width: { ideal: 1280 }, height: { ideal: 720 } }
        : { facingMode: { ideal: "user" }, width: { ideal: 1280 }, height: { ideal: 720 } };
      try {
        return await navigator.mediaDevices.getUserMedia({ video: videoConstraints, audio: false });
      } catch (error) {
        if (error.name !== "OverconstrainedError" || deviceId) throw error;
        return navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      }
    }

    async function start(deviceId) {
      if (!navigator.mediaDevices?.getUserMedia) {
        onError("Camera access needs localhost or HTTPS in a browser that supports webcam access.");
        return false;
      }
      try {
        const nextStream = await requestCamera(deviceId);
        const previousStream = stream;
        stream = nextStream;
        video.srcObject = nextStream;
        video.hidden = false;
        video.muted = true;
        video.playsInline = true;
        try {
          if (video.readyState < HTMLMediaElement.HAVE_METADATA) {
            await new Promise((resolve, reject) => {
              const timeout = window.setTimeout(() => reject(new Error("Camera stream timed out.")), 8000);
              video.addEventListener("loadedmetadata", () => { window.clearTimeout(timeout); resolve(); }, { once: true });
              video.addEventListener("error", () => { window.clearTimeout(timeout); reject(new Error("Camera video could not be loaded.")); }, { once: true });
            });
          }
          await video.play();
        } catch (playError) {
          nextStream.getTracks().forEach((track) => track.stop());
          video.srcObject = null;
          throw playError;
        }
        previousStream?.getTracks().forEach((track) => track.stop());
        await enumerateCameras();
        return true;
      } catch (error) {
        onError(cameraError(error));
        return false;
      }
    }

    async function switchCamera() {
      if (devices.length < 2) {
        onError("Only one camera is available on this device.");
        return false;
      }
      const currentIndex = devices.findIndex((device) => device.deviceId === picker.value);
      const nextDevice = devices[(currentIndex + 1) % devices.length];
      picker.value = nextDevice.deviceId;
      const changed = await start(nextDevice.deviceId);
      if (!changed && stream) picker.value = stream.getVideoTracks()[0]?.getSettings().deviceId || "";
      return changed;
    }

    picker.addEventListener("change", async () => {
      const changed = await start(picker.value);
      if (!changed && stream) picker.value = stream.getVideoTracks()[0]?.getSettings().deviceId || "";
    });

    navigator.mediaDevices?.addEventListener?.("devicechange", enumerateCameras);

    return {
      start: () => start(),
      stop: () => {
        stream?.getTracks().forEach((track) => track.stop());
        stream = null;
        video.srcObject = null;
        navigator.mediaDevices?.removeEventListener?.("devicechange", enumerateCameras);
      },
      switchCamera,
    };
  }

  window.createCameraController = createCameraController;
})();
