"use strict";

document.addEventListener("DOMContentLoaded", () => {
    const providerSelect = document.querySelector("[data-provider-select]");
    const modelSelect = document.querySelector("[data-model-select]");

    if (providerSelect && modelSelect) {
        const modelProviders = {
            "local-synthetic-v1": "synthetic",
            "openai/gpt-oss-20b": "groq",
        };

        function filterModels() {
            const provider = providerSelect.value;
            Array.from(modelSelect.options).forEach((option) => {
                const optionProvider = modelProviders[option.value];
                option.hidden = Boolean(optionProvider && optionProvider !== provider);
            });
            const selected = modelSelect.options[modelSelect.selectedIndex];
            if (selected && selected.hidden) {
                modelSelect.value = "";
            }
        }

        providerSelect.addEventListener("change", filterModels);
        filterModels();
    }

    document.querySelectorAll("[data-voice-input]").forEach((button) => {
        const target = document.getElementById(button.dataset.voiceInput);
        const status = button.closest(".knowledge-editor")?.querySelector("[data-voice-status]");
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

        if (!target || !SpeechRecognition) {
            button.disabled = true;
            if (status) {
                status.textContent = "Voice input is not supported by this browser. You can still type normally.";
            }
            return;
        }

        const recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = false;
        recognition.lang = document.documentElement.lang || "en-US";

        button.addEventListener("click", () => {
            if (button.dataset.listening === "true") {
                recognition.stop();
                return;
            }
            recognition.start();
            button.dataset.listening = "true";
            button.classList.add("is-listening");
            button.setAttribute("aria-label", "Stop voice input");
            button.title = "Stop voice input";
            if (status) {
                status.textContent = "Listening… speak clearly, then stop when finished.";
            }
        });

        recognition.addEventListener("result", (event) => {
            const transcript = Array.from(event.results)
                .slice(event.resultIndex)
                .map((result) => result[0].transcript)
                .join(" ")
                .trim();
            if (transcript) {
                target.value = target.value.trim()
                    ? `${target.value.trim()}\n${transcript}`
                    : transcript;
                target.dispatchEvent(new Event("input", { bubbles: true }));
            }
        });

        recognition.addEventListener("error", (event) => {
            button.dataset.listening = "false";
            button.classList.remove("is-listening");
            button.setAttribute("aria-label", "Start voice input");
            button.title = "Start voice input";
            if (status) {
                status.textContent = `Voice input error: ${event.error}. You can continue typing.`;
            }
        });

        recognition.addEventListener("end", () => {
            button.dataset.listening = "false";
            button.classList.remove("is-listening");
            button.setAttribute("aria-label", "Start voice input");
            button.title = "Start voice input";
            if (status && status.textContent.startsWith("Listening")) {
                status.textContent = "Voice input stopped. Review the transcript before saving.";
            }
        });
    });

    document.querySelectorAll("input[type='file'][name='source_file']").forEach((input) => {
        const label = input.closest(".knowledge-editor")?.querySelector("[data-file-name]");
        input.addEventListener("change", () => {
            if (label) {
                label.textContent = input.files.length
                    ? input.files[0].name
                    : "No file attached";
            }
        });
    });

    const filterInput = document.querySelector("[data-table-filter]");
    const tableBody = document.querySelector("[data-filter-table]");

    if (!filterInput || !tableBody) {
        return;
    }

    const rows = Array.from(
        tableBody.querySelectorAll("[data-filter-row]")
    );
    const emptyState = tableBody.querySelector("[data-filter-empty]");

    function filterRows() {
        const query = filterInput.value.trim().toLocaleLowerCase();
        let visibleCount = 0;

        rows.forEach((row) => {
            const matches = row.textContent
                .toLocaleLowerCase()
                .includes(query);

            row.hidden = !matches;

            if (matches) {
                visibleCount += 1;
            }
        });

        if (emptyState) {
            emptyState.hidden = visibleCount > 0;
        }
    }

    filterInput.addEventListener("input", filterRows);

    // Fallback for accordion/collapse elements if Bootstrap JS is unavailable offline
    document.querySelectorAll("[data-bs-toggle='collapse']").forEach((btn) => {
        btn.addEventListener("click", () => {
            if (window.bootstrap && window.bootstrap.Collapse) {
                return;
            }
            const targetSelector = btn.getAttribute("data-bs-target");
            const target = targetSelector ? document.querySelector(targetSelector) : null;
            if (target) {
                const isOpen = target.classList.contains("show");
                target.classList.toggle("show", !isOpen);
                btn.classList.toggle("collapsed", isOpen);
                btn.setAttribute("aria-expanded", String(!isOpen));
            }
        });
    });
});