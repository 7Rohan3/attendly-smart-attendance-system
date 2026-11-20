(() => {
  const video = document.getElementById("camera");
  const canvas = document.getElementById("capture-canvas");
  const placeholder = document.getElementById("camera-placeholder");
  const captureButton = document.getElementById("capture-attendance");
  const message = document.getElementById("attendance-message");
  const camera = window.createCameraController(
    video,
    document.getElementById("camera-select"),
    (error) => showMessage(error, "error"),
  );

  function showMessage(text, state = "") {
    message.className = `result-message${state ? ` result-${state}` : ""}`;
    message.querySelector("span:last-child").textContent = text;
  }

  document.getElementById("switch-camera").addEventListener("click", () => {
    camera.switchCamera();
  });

  captureButton.addEventListener("click", async () => {
    if (!video.srcObject || !video.videoWidth) {
      showMessage("Camera is not ready. Allow camera access and try again.", "error");
      return;
    }
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    captureButton.disabled = true;
    captureButton.textContent = "Checking…";
    showMessage("Checking face…");
    try {
      const response = await fetch("/api/attendance", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]')?.content || "" },
        body: JSON.stringify({ image: canvas.toDataURL("image/jpeg", 0.9) }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Could not mark attendance.");
      showMessage(`${result.message} (${result.time}) · face distance ${result.distance}`, "success");
    } catch (error) {
      showMessage(error.message || "Could not reach the server. Please try again.", "error");
    } finally {
      captureButton.disabled = false;
      captureButton.innerHTML = "◎ Capture &amp; check in";
    }
  });

  camera.start().then((started) => {
    if (started) {
      const reveal = () => {
        if (video.videoWidth > 0 && video.videoHeight > 0) {
          placeholder.hidden = true;
          showMessage("Camera ready. Position your face in the frame.");
        }
      };
      video.addEventListener("loadeddata", reveal, { once: true });
      reveal();
    }
  });
  window.addEventListener("beforeunload", camera.stop);
})();
