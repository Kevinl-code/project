function customAlert(message) {
            const alertBox = document.createElement("div");
            alertBox.classList.add("custom-alert");
            alertBox.innerHTML = `<p>${message}</p><button onclick="this.parentElement.remove()">OK</button>`;
            document.body.appendChild(alertBox);
        }

        window.alert = function (message) {
            customAlert(message);
        };

        function showContent(page) {
            document.querySelectorAll('.content').forEach(content => content.style.display = 'none');
            document.getElementById(`${page}-content`).style.display = 'block';
        }

        window.onload = () => showContent('import');

        document.getElementById('import-data-btn').addEventListener('click', () => {
            if (!document.getElementById('file-uploader').files.length) {
                customAlert('Please upload an XLSX file first.');
                return;
            }
            document.getElementById('table-name-container').style.display = 'block';
        });

        document.getElementById('start-import-btn').addEventListener('click', async () => {
            const tableName = document.getElementById('table-name').value.trim();
            const file = document.getElementById('file-uploader').files[0];

            if (!tableName || !file) {
                customAlert('Please provide both file and table name.');
                return;
            }

            const formData = new FormData();
            formData.append('file', file);
            formData.append('table_name', tableName);

            try {
                const response = await fetch('/upload', { method: 'POST', body: formData });
                const result = await response.json();

                customAlert(result.message);
                if (result.success) showContent('category');
            } catch (error) {
                customAlert('An error occurred while importing data.');
            }
        });

        function navigateToExport() {
            showContent('export');
        }
