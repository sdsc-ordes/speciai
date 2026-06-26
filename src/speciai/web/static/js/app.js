// progress page: subscribe to stage events, advance the stepper and bar.
;(function () {
  const jobId = window.SPECIAI_JOB_ID
  if (!jobId) return
  const step = (stage) => document.querySelector(`.step[data-stage="${stage}"]`)
  const fill = document.getElementById("progress-fill")
  const pct = document.getElementById("progress-pct")

  // Pipeline stages drive the bar; the synthetic "done" step is not one of them.
  const total =
    [...document.querySelectorAll(".step[data-stage]")].filter(
      (li) => li.dataset.stage !== "done",
    ).length || 1
  let finished = 0

  const setProgress = (fraction, complete) => {
    const value = Math.round(Math.min(fraction, 1) * 100)
    if (fill) {
      fill.style.width = value + "%"
      if (complete) fill.classList.add("complete")
    }
    if (pct) pct.textContent = value + "%"
  }

  const src = new EventSource(`/jobs/${jobId}/events`)
  src.onmessage = (e) => {
    const msg = JSON.parse(e.data)
    if (msg.status === "done") {
      src.close()
      setProgress(1, true)
      const last = step("done")
      if (last) last.classList.add("done")
      window.location.href = `/jobs/${jobId}/review`
      return
    }
    if (msg.status === "error") {
      src.close()
      const active = document.querySelector(".step.running")
      if (active) active.classList.replace("running", "error")
      document.querySelector("h1").textContent =
        "Pipeline failed: " + (msg.error || "")
      return
    }
    const li = step(msg.stage)
    if (!li) return
    if (msg.status === "started") {
      li.classList.add("running")
      setProgress((finished + 0.5) / total) // mid-step motion
    } else if (msg.status === "finished") {
      li.classList.remove("running")
      li.classList.add("done")
      finished += 1
      setProgress(finished / total)
    }
  }
})()
