let selectedEvent = null;

async function loadDesks() {
    const response = await fetch('/desks');
    const desks = await response.json();
    const desksDiv = document.getElementById('desks');
    desksDiv.innerHTML = desks.map(desk =>
        `<div class="desk ${desk.available ? 'available' : 'reserved'}" data-id="${desk.id}">
            ${desk.name}
        </div>`).join('');

    document.querySelectorAll('.desk.available').forEach(desk => {
        desk.addEventListener('click', () => {
            document.querySelectorAll('.desk').forEach(d => d.classList.remove('selected'));
            desk.classList.add('selected');
            document.getElementById('desk_id').value = desk.dataset.id;
            loadReservations(desk.dataset.id);
            loadCalendar(desk.dataset.id);
        });
    });
}

async function loadReservations(deskId) {
    const response = await fetch(`/reservations/${deskId}`);
    const reservations = await response.json();

    const reservationListDiv = document.getElementById('reservation_list');
    reservationListDiv.innerHTML = '<h2>Reserved Times</h2>';

    if (reservations.length === 0) {
        reservationListDiv.innerHTML += '<p>No reservations for this desk.</p>';
    } else {
        const list = document.createElement('ul');
        reservations.forEach(reservation => {
            const listItem = document.createElement('li');
            const start = new Date(reservation.start_time);
            const end = new Date(reservation.end_time);
            listItem.textContent = `${start.toLocaleString()} - ${end.toLocaleString()}`;
            list.appendChild(listItem);
        });
        reservationListDiv.appendChild(list);
    }
}

async function loadCalendar(deskId) {
    const today = new Date();
    const year = today.getFullYear();
    const month = today.getMonth() + 1;
    const response = await fetch(`/reservations/${deskId}/month/${year}/${month}`);
    const daysStatus = await response.json();

    const calendarEl = document.getElementById('calendar');
    const calendar = new FullCalendar.Calendar(calendarEl, {
        initialView: 'dayGridMonth',
        events: Object.keys(daysStatus).map(day => ({
            start: `${year}-${month < 10 ? '0' : ''}${month}-${day < 10 ? '0' : ''}${day}`,
            display: 'background',
            color: daysStatus[day] === 'reserved' ? 'red' : daysStatus[day] === 'partial' ? 'orange' : 'green'
        })),
        dateClick: function(info) {
            const clickedDate = new Date(info.dateStr);
            if (clickedDate < today.setHours(0, 0, 0, 0)) {
                showError("You cannot select a past date.");
                return;
            }

            // Unselect the previously selected date
            if (selectedEvent) {
                selectedEvent.remove();
            }

            document.getElementById('reserveForm').style.display = 'block';
            document.getElementById('selected_date').textContent = info.dateStr;
            document.getElementById('date').value = info.dateStr;
            loadTimes(deskId, info.dateStr);

            // Highlight the selected date
            selectedEvent = calendar.addEvent({
                start: info.dateStr,
                display: 'background',
                color: 'yellow'
            });
        }
    });

    calendar.render();
}

async function loadTimes(deskId, date) {
    const response = await fetch(`/reservations/${deskId}`);
    const reservations = await response.json();

    const times = Array.from({ length: 15 }, (_, i) => i + 8).map(hour => {
        const time = `${hour < 10 ? '0' : ''}${hour}:00`;
        const reserved = reservations.some(reservation => {
            const start = new Date(reservation.start_time);
            const end = new Date(reservation.end_time);
            return start <= new Date(`${date}T${time}`) && end > new Date(`${date}T${time}`);
        });
        return { time, reserved };
    });

    const startTimeElem = document.getElementById('start_time');
    const endTimeElem = document.getElementById('end_time');

    startTimeElem.innerHTML = '';
    endTimeElem.innerHTML = '';

    times.forEach(({ time, reserved }) => {
        const option = document.createElement('option');
        option.value = time;
        option.textContent = time;
        option.disabled = reserved;
        startTimeElem.appendChild(option.cloneNode(true));
        endTimeElem.appendChild(option.cloneNode(true));
    });

    endTimeElem.addEventListener('change', function () {
        const selectedStartTime = startTimeElem.value;
        const selectedEndTime = endTimeElem.value;
        if (selectedStartTime >= selectedEndTime) {
            showError('End time must be after start time.');
            endTimeElem.value = '';
        } else {
            hideError();
        }
    });
}

document.addEventListener('DOMContentLoaded', () => {
    loadDesks();

    document.getElementById('reserveForm').addEventListener('submit', async (event) => {
        event.preventDefault();
        const date = document.getElementById('date').value;
        const startTime = document.getElementById('start_time').value;
        const endTime = document.getElementById('end_time').value;
        const deskId = document.getElementById('desk_id').value;

        const startDatetime = `${date}T${startTime}`;
        const endDatetime = `${date}T${endTime}`;

        // Validate times
        if (new Date(startDatetime) >= new Date(endDatetime)) {
            showError("End time must be after start time.");
            return;
        }

        const formData = new FormData();
        formData.append('start_datetime', startDatetime);
        formData.append('end_datetime', endDatetime);
        formData.append('desk_id', deskId);

        try {
            const response = await fetch('/reserve_desk', {
                method: 'POST',
                body: formData
            });

            // Check if response is ok (status 200-299)
            if (response.ok) {
                window.location.href = '/reservation_info';
            } else {
                const result = await response.json();
                showError(result.message);
            }
        } catch (error) {
            showError("An error occurred while making the reservation.");
            console.error('Error:', error);
        }
    });

    loadDesks();
});

function showError(message) {
    const errorMessage = document.getElementById('error-message');
    errorMessage.textContent = message;
    errorMessage.style.display = 'block';
}

function hideError() {
    const errorMessage = document.getElementById('error-message');
    errorMessage.style.display = 'none';
}
