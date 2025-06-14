document.addEventListener('DOMContentLoaded', function() {
    // --- Medication Alert Modal Logic ---
    const medicationAlertModal = document.getElementById('medicationAlertModal');
    const dismissAlertBtn = document.getElementById('dismissAlertBtn');
    const medicationDetails = document.getElementById('medicationDetails');
    const alertSound = document.getElementById('alertSound');
    let alertedMedications = new Set(); // To prevent re-alerting for the same medication/time

    function playAlertSound() {
        if (alertSound) {
            // Check if play is allowed, often requires user interaction first
            alertSound.play().catch(e => console.error("Error playing sound:", e));
        }
    }

    function showMedicationAlert(med) {
        // Create a unique ID for the alert to prevent duplicates
        const alertId = `${med.name}-${med.due_time}`;
        if (alertedMedications.has(alertId)) {
            return; // Already alerted for this medication at this time
        }
        alertedMedications.add(alertId);

        medicationDetails.innerHTML = `
            <p><strong>Medication:</strong> ${med.name}</p>
            <p><strong>Dosage:</strong> ${med.dosage}</p>
            <p><strong>Instructions:</strong> ${med.instructions}</p>
            <p><strong>Frequency:</strong> ${med.frequency}</p>
            <p><strong>Due Time:</strong> ${med.due_time}</p>
        `;
        medicationAlertModal.classList.remove('hidden');
        playAlertSound();
    }

    dismissAlertBtn.addEventListener('click', function() {
        medicationAlertModal.classList.add('hidden');
        alertSound.pause();
        alertSound.currentTime = 0; // Reset sound to beginning
        // Optionally, clear only the dismissed alert, or all if preferred
        alertedMedications.clear(); // Clear all current alerts when dismissed
    });

    async function checkForDueMedications() {
        try {
            const response = await fetch('/patient/api/due_medications');
            if (!response.ok) {
                console.error('Failed to fetch due medications:', response.status, response.statusText);
                return;
            }
            const data = await response.json();
            if (data.due_medications && data.due_medications.length > 0) {
                data.due_medications.forEach(med => {
                    showMedicationAlert(med);
                });
            }
        } catch (error) {
            console.error('Error fetching due medications:', error);
        }
    }

    // Check for due medications every minute
    setInterval(checkForDueMedications, 60 * 1000);
    // Initial check on page load
    checkForDueMedications();

    // --- Next Dose Countdown Logic ---
    const nextDoseCountdownEl = document.getElementById('nextDoseCountdown');
    const nextDoseTimestampEl = document.getElementById('nextDoseTimestamp');

    if (nextDoseCountdownEl && nextDoseTimestampEl) {
        const nextDoseUnixTimestampStr = nextDoseTimestampEl.value;
        if (nextDoseUnixTimestampStr) {
            const nextDoseUnixTimestamp = parseInt(nextDoseUnixTimestampStr);
            // JavaScript Date constructor expects milliseconds for Unix timestamp
            const nextDoseDateTime = new Date(nextDoseUnixTimestamp);

            function updateNextDoseCountdown() {
                const now = new Date().getTime(); // Current time in milliseconds
                let distance = nextDoseDateTime.getTime() - now; // Difference in milliseconds

                if (distance < 0) {
                    nextDoseCountdownEl.textContent = 'Due Now!';
                    clearInterval(countdownInterval); // Stop the countdown
                    checkForDueMedications(); // Re-check for new due meds
                    return;
                }

                const hours = Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
                const minutes = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));
                const seconds = Math.floor((distance % (1000 * 60)) / 1000);

                nextDoseCountdownEl.textContent =
                    `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
            }

            const countdownInterval = setInterval(updateNextDoseCountdown, 1000);
            updateNextDoseCountdown(); // Initial call to display immediately
        } else {
            nextDoseCountdownEl.textContent = 'N/A'; // No next dose scheduled
        }
    }
});