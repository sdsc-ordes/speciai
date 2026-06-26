// progress page: subscribe to stage events and advance the stepper.
(function () {
  const jobId = window.SPECIAI_JOB_ID;
  if (!jobId) return;
  const step = (stage) => document.querySelector(`.step[data-stage="${stage}"]`);
  const src = new EventSource(`/jobs/${jobId}/events`);
  src.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.status === "done") {
      src.close();
      const last = step("done");
      if (last) last.classList.add("done");
      window.location.href = `/jobs/${jobId}/review`;
      return;
    }
    if (msg.status === "error") {
      src.close();
      const active = document.querySelector(".step.running");
      if (active) active.classList.replace("running", "error");
      document.querySelector("h1").textContent =
        "Pipeline failed: " + (msg.error || "");
      return;
    }
    const li = step(msg.stage);
    if (!li) return;
    if (msg.status === "started") {
      li.classList.add("running");
    } else if (msg.status === "finished") {
      li.classList.remove("running");
      li.classList.add("done");
    }
  };
})();
