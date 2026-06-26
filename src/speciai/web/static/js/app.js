// progress page: subscribe to stage events and advance the stepper.
(function () {
  const jobId = window.SPECIAI_JOB_ID;
  if (!jobId) return;
  const src = new EventSource(`/jobs/${jobId}/events`);
  src.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.status === "done") {
      src.close();
      window.location.href = `/jobs/${jobId}/review`;
      return;
    }
    if (msg.status === "error") {
      src.close();
      document.querySelector("h1").textContent = "Pipeline failed: " + (msg.error || "");
      return;
    }
    const li = document.querySelector(`.step[data-stage="${msg.stage}"]`);
    if (li) li.classList.toggle("done", msg.status === "finished");
  };
})();
