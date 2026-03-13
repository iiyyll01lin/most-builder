const output = document.getElementById("output");
const loginStatus = document.getElementById("login-status");

let token = null;

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new Error(data?.detail || response.statusText);
  }
  return data;
}

function render(data) {
  output.textContent = JSON.stringify(data, null, 2);
}

document.getElementById("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const username = document.getElementById("username").value;
  const password = document.getElementById("password").value;
  try {
    const result = await api("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    token = result.access_token;
    loginStatus.textContent = `Signed in as ${result.user.name} (${result.user.role})`;
    render(result);
  } catch (error) {
    loginStatus.textContent = error.message;
  }
});

document.getElementById("health-btn").addEventListener("click", async () => render(await api("/api/v1/health")));
document.getElementById("projects-btn").addEventListener("click", async () => render(await api("/api/v1/projects")));
document.getElementById("versions-btn").addEventListener("click", async () => render(await api("/api/v1/sop/versions")));
document.getElementById("db-btn").addEventListener("click", async () => render(await api("/api/v1/db/status")));
