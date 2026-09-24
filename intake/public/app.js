const status = document.querySelector('#status');
const button = document.querySelector('#check');

async function checkConnection() {
  button.disabled = true;
  status.textContent = 'Connecting to the backend…';

  try {
    const response = await fetch('/api/health', {
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (data.status !== 'ok') throw new Error('Unexpected backend response');
    status.textContent = 'Python backend connected.';
  } catch (error) {
    status.textContent = 'Could not reach the backend. Check that server.py is running.';
    console.error(error);
  } finally {
    button.disabled = false;
  }
}

button.addEventListener('click', checkConnection);
checkConnection();
