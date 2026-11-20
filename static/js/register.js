(() => {
  const video = document.getElementById("camera");
  const canvas = document.getElementById("capture-canvas");
  const placeholder = document.getElementById("camera-placeholder");
  const form = document.getElementById("register-form");
  const fileInput = document.getElementById("photo-file");
  const photoStatus = document.getElementById("photo-status");
  const message = document.getElementById("form-message");
  const camera = window.createCameraController(
    video,
    document.getElementById("camera-select"),
    (error) => { photoStatus.textContent = error; },
  );
  let selectedImage = "";

  camera.start().then((started) => {
    if (started) {
      const reveal = () => { if (video.videoWidth > 0 && video.videoHeight > 0) placeholder.hidden = true; };
      video.addEventListener("loadeddata", reveal, { once: true });
      reveal();
    } else photoStatus.textContent += " Choose a photo to continue.";
  });

  document.getElementById("capture-photo").addEventListener("click", () => {
    if (!video.srcObject || !video.videoWidth) {
      photoStatus.textContent = "Camera is not ready. Choose a photo or allow camera access.";
      return;
    }
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    selectedImage = canvas.toDataURL("image/jpeg", 0.9);
    photoStatus.textContent = "Photo captured and ready to register.";
    message.textContent = "";
  });

  document.getElementById("switch-camera").addEventListener("click", () => {
    camera.switchCamera();
  });

  fileInput.addEventListener("change", () => {
    const file = fileInput.files?.[0];
    if (!file) return;
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
      selectedImage = "";
      photoStatus.textContent = "Choose a JPEG, PNG, or WebP image.";
      return;
    }
    if (file.size > 4 * 1024 * 1024) {
      selectedImage = "";
      photoStatus.textContent = "Choose an image smaller than 4 MB.";
      return;
    }
    const reader = new FileReader();
    reader.addEventListener("load", () => {
      selectedImage = reader.result;
      photoStatus.textContent = `${file.name} selected and ready to register.`;
      message.textContent = "";
    });
    reader.addEventListener("error", () => {
      photoStatus.textContent = "Could not read that image. Choose it again.";
    });
    reader.readAsDataURL(file);
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector('[type="submit"]');
    const formData = new FormData(form);
    message.className = "message";
    message.textContent = "";
    if (!selectedImage) {
      message.classList.add("message-error");
      message.textContent = "Capture a photo or choose an image before registering.";
      return;
    }
    button.disabled = true;
    button.textContent = "Registering…";
    try {
      const response = await fetch("/api/students", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]')?.content || "" },
        body: JSON.stringify({
          student_id: formData.get("student_id"),
          full_name: formData.get("full_name"),
          email: formData.get("email"),
          department: formData.get("department"),
          image: selectedImage,
        }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Registration failed.");
      message.classList.add("message-success");
      message.textContent = result.message;
      form.reset();
      selectedImage = "";
      photoStatus.textContent = "No face photo selected yet.";
    } catch (error) {
      message.classList.add("message-error");
      message.textContent = error.message || "Could not reach the server. Please try again.";
    } finally {
      button.disabled = false;
      button.innerHTML = 'Register student <span>→</span>';
    }
  });

  document.querySelectorAll(".deactivate-student").forEach((button) => button.addEventListener("click", async () => {
    if (!window.confirm(`Deactivate ${button.dataset.id}? Attendance history will remain.`)) return;
    const response = await fetch(`/api/students/${encodeURIComponent(button.dataset.id)}/deactivate`, {
      method: "POST", headers: { "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]')?.content || "" },
    });
    const result = await response.json();
    if (!response.ok) { window.alert(result.error || "Could not deactivate student."); return; }
    window.location.reload();
  }));

  document.querySelectorAll(".edit-student").forEach((button) => button.addEventListener("click", async () => {
    const full_name = window.prompt("Full name", button.dataset.name);
    if (full_name === null) return;
    const email = window.prompt("Email (optional)", button.dataset.email);
    if (email === null) return;
    const department = window.prompt("Department", button.dataset.department);
    if (department === null) return;
    const response = await fetch(`/api/students/${encodeURIComponent(button.dataset.id)}/edit`, {
      method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]')?.content || "" },
      body: JSON.stringify({ full_name, email, department }),
    });
    const result = await response.json();
    if (!response.ok) { window.alert(result.error || "Could not update student."); return; }
    window.location.reload();
  }));

  window.addEventListener("beforeunload", camera.stop);
})();
