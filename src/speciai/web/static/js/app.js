// progress page: subscribe to stage events, advance the stepper and bar.
;(function () {
  const jobId = window.SPECIAI_JOB_ID
  if (!jobId) return
  const step = (stage) => document.querySelector(`.step[data-stage="${stage}"]`)
  const fill = document.getElementById("progress-fill")
  const pct = document.getElementById("progress-pct")

  // Client-side stage timing: record when each stage's "started" event arrives
  // and render the elapsed wall-clock time when its "finished" event lands. The
  // pipeline is synchronous, so browser-observed duration tracks the real stage
  // time (bar the negligible SSE hop).
  const startedAt = {}
  const formatDuration = (ms) => {
    if (ms < 1000) return Math.round(ms) + " ms"
    const s = ms / 1000
    return (s < 10 ? s.toFixed(1) : Math.round(s)) + " s"
  }
  const showTime = (li, text) => {
    const el = li.querySelector(".step-time")
    if (el) el.textContent = text
  }

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
      startedAt[msg.stage] = performance.now()
      setProgress((finished + 0.5) / total) // mid-step motion
    } else if (msg.status === "finished") {
      li.classList.remove("running")
      li.classList.add("done")
      const start = startedAt[msg.stage]
      if (start !== undefined)
        showTime(li, formatDuration(performance.now() - start))
      finished += 1
      setProgress(finished / total)
    }
  }
})()

// review page: re-derive a section's inferred fields from its verbatim source.
;(function () {
  const buttons = document.querySelectorAll(".rederive")
  if (!buttons.length) return

  const setMessage = (btn, text) => {
    const msg = btn.parentElement.querySelector(".rederive-msg")
    if (msg) msg.textContent = text || ""
  }

  buttons.forEach((btn) => {
    btn.addEventListener("click", async () => {
      const source = btn.dataset.source
      const fieldName = btn.dataset.field
      const input = document.querySelector(`[name="${fieldName}"]`)
      const value = input ? input.value : ""
      btn.disabled = true
      btn.classList.add("loading")
      setMessage(btn, "")
      try {
        const resp = await fetch(`/derive/${source}`, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: new URLSearchParams({ [fieldName]: value }),
        })
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}))
          throw new Error(err.detail || "Lookup failed")
        }
        const data = await resp.json()
        for (const [name, val] of Object.entries(data.fields)) {
          const el = document.querySelector(`[name="${name}"]`)
          if (!el) continue
          el.value = val
          // Surface a freshly-filled field hidden inside a collapsed group.
          const details = el.closest("details.empties")
          if (details && val !== "") details.open = true
        }
      } catch (e) {
        setMessage(btn, e.message)
      } finally {
        btn.disabled = false
        btn.classList.remove("loading")
      }
    })
  })

  // Enter inside a field re-derives that field (when derivable) rather than
  // submitting the form; export stays explicit via the Export buttons.
  const form = document.querySelector(".record-form")
  if (form) {
    form.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" || e.target.tagName !== "INPUT") return
      e.preventDefault()
      const btn = form.querySelector(`.rederive[data-field="${e.target.name}"]`)
      if (btn) btn.click()
    })
  }
})()
