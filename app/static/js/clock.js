  function updateClock() {
            const now = new Date();

            // Format options
            const options = { weekday: 'long', year: 'numeric', month: 'short', day: 'numeric' };
            const dateStr = now.toLocaleDateString('en-US', options);

            const timeStr = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

            document.getElementById("clock").innerHTML = dateStr + " | " + timeStr;
        }

        setInterval(updateClock, 1000);
        updateClock(); // Initial call