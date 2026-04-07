let scene, camera, renderer, controls, model;

const viewer = document.getElementById("viewer");
const fileInput = document.getElementById("fileInput");

document.addEventListener('DOMContentLoaded', function() {
    initScene();
});

fileInput.addEventListener("change", handleFileUpload);
window.addEventListener('resize', onWindowResize);

function initScene() {
    console.log("Инициализация сцены...");

    if (typeof THREE === 'undefined') {
        console.error('THREE не загружен');
        return;
    }

    // Сцена
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf7f7f7);

    // Камера
    camera = new THREE.PerspectiveCamera(
        45,
        viewer.clientWidth / viewer.clientHeight,
        0.1,
        1000
    );
    camera.position.set(0, 0, 10);

    // Рендерер
    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(viewer.clientWidth, viewer.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    viewer.appendChild(renderer.domElement);

    // Освещение
    const directionalLight = new THREE.DirectionalLight(0xffffff, 1);
    directionalLight.position.set(5, 5, 5);
    scene.add(directionalLight);

    const ambientLight = new THREE.AmbientLight(0x404040, 0.6);
    scene.add(ambientLight);

    // OrbitControls
    if (typeof THREE.OrbitControls !== 'undefined') {
        controls = new THREE.OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.05;
    }

    // Оси и сетка
    // const axesHelper = new THREE.AxesHelper(2);
    // scene.add(axesHelper);
    //
    // const gridHelper = new THREE.GridHelper(10, 10);
    // scene.add(gridHelper);

    animate();

    console.log("Сцена инициализирована");
}

function animate() {
    requestAnimationFrame(animate);
    if (controls) {
        controls.update();
    }
    renderer.render(scene, camera);
}

function handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    console.log("Загрузка файла:", file.name);

    const reader = new FileReader();
    const extension = file.name.split(".").pop().toLowerCase();

    reader.onload = function (e) {
        try {
            const contents = e.target.result;

            if (model) {
                scene.remove(model);
                if (model.geometry) model.geometry.dispose();
                if (model.material) {
                    if (Array.isArray(model.material)) {
                        model.material.forEach(material => material.dispose());
                    } else {
                        model.material.dispose();
                    }
                }
            }

            let loader;
            let material = new THREE.MeshStandardMaterial({
                color: getColorForExtension(extension),
                roughness: 0.7,
                metalness: 0.1
            });

            switch (extension) {
                case "obj":
                    if (typeof THREE.OBJLoader === 'undefined') {
                        throw new Error('OBJLoader не загружен');
                    }
                    loader = new THREE.OBJLoader();
                    model = loader.parse(contents);
                    model.traverse((child) => {
                        if (child.isMesh) {
                            child.material = material;
                        }
                    });
                    break;

                case "stl":
                    if (typeof THREE.STLLoader === 'undefined') {
                        throw new Error('STLLoader не загружен');
                    }
                    loader = new THREE.STLLoader();
                    const geometrySTL = loader.parse(contents);
                    model = new THREE.Mesh(geometrySTL, material);
                    break;

                case "ply":
                    if (typeof THREE.PLYLoader === 'undefined') {
                        throw new Error('PLYLoader не загружен');
                    }
                    loader = new THREE.PLYLoader();
                    const geometryPLY = loader.parse(contents);
                    geometryPLY.computeVertexNormals();
                    model = new THREE.Mesh(geometryPLY, material);
                    break;

                default:
                    alert("Неподдерживаемый формат файла: " + extension);
                    return;
            }

            scene.add(model);
            centerModel(model);
            if (controls) controls.reset();

            console.log("Модель успешно загружена:", extension);

        } catch (error) {
            console.error("Ошибка при загрузке модели:", error);
            alert("Ошибка при загрузке файла: " + error.message);

            createDemoGeometry(extension);
        }
    };

    reader.onerror = function(error) {
        console.error("Ошибка чтения файла:", error);
        alert("Ошибка чтения файла");
    };

    if (extension === "obj") {
        reader.readAsText(file);
    } else {
        reader.readAsArrayBuffer(file);
    }
}

function createDemoGeometry(extension) {
    let geometry;
    const material = new THREE.MeshStandardMaterial({
        color: getColorForExtension(extension),
        wireframe: true
    });

    switch (extension) {
        case "obj":
            geometry = new THREE.BoxGeometry(2, 2, 2);
            break;
        case "stl":
            geometry = new THREE.ConeGeometry(1, 2, 8);
            break;
        case "ply":
            geometry = new THREE.SphereGeometry(1, 16, 16);
            break;
        default:
            geometry = new THREE.BoxGeometry(1, 1, 1);
    }

    model = new THREE.Mesh(geometry, material);
    scene.add(model);
    centerModel(model);
}

function centerModel(model) {
    const box = new THREE.Box3().setFromObject(model);
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());

    model.position.x = -center.x;
    model.position.y = -center.y;
    model.position.z = -center.z;

    const maxDim = Math.max(size.x, size.y, size.z);
    const fov = camera.fov * (Math.PI / 180);
    let cameraZ = Math.abs(maxDim / Math.sin(fov / 2));

    cameraZ = Math.max(cameraZ, maxDim * 1.5);
    camera.position.set(0, 0, cameraZ);
    camera.lookAt(0, 0, 0);

    if (controls) controls.update();
}

function getColorForExtension(extension) {
    switch (extension) {
        case "obj": return 0x0077ff;
        case "stl": return 0xff7700;
        case "ply": return 0x22aa22;
        default: return 0x888888;
    }
}

function onWindowResize() {
    if (camera && renderer) {
        camera.aspect = viewer.clientWidth / viewer.clientHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(viewer.clientWidth, viewer.clientHeight);
    }
}

async function analyzeModel() {
    if (!model) {
        alert('Пожалуйста, сначала загрузите модель');
        return;
    }

    const analyzeBtn = document.getElementById('analyzeBtn');
    analyzeBtn.disabled = true;
    analyzeBtn.textContent = 'Анализ...';

    try {
        const fileInput = document.getElementById('fileInput');
        const file = fileInput.files[0];

        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch('http://localhost:8000/api/analyze', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (result.success) {
            displayMetrics(result.metrics, result.overall_score);
        } else {
            throw new Error(result.error);
        }

    } catch (error) {
        console.error('Ошибка:', error);
        alert('Ошибка анализа: ' + error.message);
    } finally {
        analyzeBtn.disabled = false;
        analyzeBtn.textContent = 'Выполнить анализ';
    }
}


document.addEventListener('DOMContentLoaded', function() {
    const analyzeBtn = document.getElementById('analyzeBtn');
    if (analyzeBtn) {
        analyzeBtn.addEventListener('click', analyzeModel);
        console.log("Кнопка анализа привязана");
    } else {
        console.error("Кнопка analyzeBtn не найдена");
    }
});
function displayMetrics(metrics, overallScore) {
    const resultsDiv = document.getElementById('metricsList');
    if (!resultsDiv) {
        console.error('Элемент metricsList не найден');
        return;
    }

        // ========== ОТЛАДКА: вывод деталей в консоль ==========
    console.log('=== ДЕТАЛИ МЕТРИК ===');
    console.log('Все метрики:', metrics);

    if (metrics['Несвязные компоненты']) {
        console.log('Несвязные компоненты:', metrics['Несвязные компоненты']);
        console.log('  - value:', metrics['Несвязные компоненты'].value);
        console.log('  - normalized:', metrics['Несвязные компоненты'].normalized);
        console.log('  - details:', metrics['Несвязные компоненты'].details);
        console.log('  - component_sizes:', metrics['Несвязные компоненты'].details?.component_sizes);
    }

    if (metrics['Замкнутость поверхности']) {
        console.log('Замкнутость поверхности details:', metrics['Замкнутость поверхности'].details);
    }

    if (metrics['Дыры и самопересечения']) {
        console.log('Дыры и самопересечения details:', metrics['Дыры и самопересечения'].details);
    }
    console.log('========================');
    // ========== КОНЕЦ ОТЛАДКИ ==========

    resultsDiv.innerHTML = '';

    // Общая оценка сверху
    const overallDiv = document.createElement('div');
    overallDiv.className = 'overall-score';

    const overallQuality = getQualityLevel(overallScore);
    const overallBadge = `<span class="quality-badge quality-${overallQuality}">${getQualityText(overallQuality)}</span>`;

    overallDiv.innerHTML = `
        <div class="metric-name">Общая оценка качества ${overallBadge}</div>
        <div class="metric-value">${(overallScore * 100).toFixed(1)}%</div>
        <div class="metric-description">Обобщённая оценка качества модели</div>
    `;
    resultsDiv.appendChild(overallDiv);

    // Группировка метрики по категориям
    const metricGroups = {
        'geometric': {
            name: 'Геометрические метрики',
            description: 'Оценивают форму модели и распределение точек в пространстве',
            metrics: ['Равномерность плотности', 'Анализ пустот и скоплений']
        },
        'topological': {
            name: 'Топологические метрики',
            description: 'Оценивают целостность и связность модели',
            metrics: ['Замкнутость поверхности', 'Несвязные компоненты', 'Дыры и самопересечения']
        },
        'structural': {
            name: 'Структурные метрики',
            description: 'Оценивают внутреннюю организацию и гладкость модели',
            metrics: ['Равномерность площадей треугольников', 'Регулярность нормалей', 'Структурная устойчивость']
        }
    };

    for (const [groupId, groupInfo] of Object.entries(metricGroups)) {
        const groupDiv = createMetricGroup(groupId, groupInfo, metrics);
        if (groupDiv) {
            resultsDiv.appendChild(groupDiv);
        }
    }

    if (metrics.basic_info) {
        const infoDiv = document.createElement('div');
        infoDiv.className = 'metric-item';
        infoDiv.style.background = '#f0f0f0';
        infoDiv.innerHTML = `
            <div class="metric-name">Информация о модели</div>
            <div class="metric-description">
                Вершин: ${metrics.basic_info.vertices || 0}<br>
                Граней: ${metrics.basic_info.faces || 0}<br>
                Объем: ${(metrics.basic_info.volume || 0).toFixed(2)}
            </div>
        `;
        resultsDiv.appendChild(infoDiv);
    }
}

function createMetricGroup(groupId, groupInfo, metrics) {
    const groupDiv = document.createElement('div');
    groupDiv.className = 'metric-group';

    let totalScore = 0;
    let metricCount = 0;
    const groupMetrics = [];

    groupInfo.metrics.forEach(metricKey => {
        if (metrics[metricKey]) {
            const metric = metrics[metricKey];
            totalScore += metric.normalized;
            metricCount++;
            groupMetrics.push({ key: metricKey, ...metric });
        }
    });

    if (metricCount === 0) return null; // Пропуск пустых групп

    const groupAverage = totalScore / metricCount;
    const groupQuality = getQualityLevel(groupAverage);

    groupDiv.innerHTML = `
        <div class="group-header" onclick="toggleGroup(this)">
            ${groupInfo.name}
            <span class="group-score">${(groupAverage * 100).toFixed(0)}%</span>
        </div>
        <div class="group-content">
            <div class="group-metrics">
                ${groupMetrics.map(metric => createMetricItemHTML(metric)).join('')}
            </div>
        </div>
    `;

    return groupDiv;
}

function createMetricItemHTML(metric) {
    const quality = getQualityLevel(metric.normalized);
    const qualityBadge = `<span class="quality-badge quality-${quality}">${getQualityText(quality)}</span>`;

    return `
        <div class="metric-item ${quality}">
            <div class="metric-name">
                ${getMetricName(metric.key)}
                ${qualityBadge}
            </div>
            <div class="metric-value">${(metric.normalized * 100).toFixed(1)}%</div>
            <div class="metric-description">${metric.description || getMetricDescription(metric.key)}</div>
        </div>
    `;
}

function toggleGroup(header) {
    const content = header.nextElementSibling;
    const isExpanded = content.classList.contains('expanded');

    if (isExpanded) {
        content.classList.remove('expanded');
        header.classList.remove('expanded');
    } else {
        content.classList.add('expanded');
        header.classList.add('expanded');
    }
}

function getMetricName(key) {
    return key;
}

function getMetricDescription(key) {
    const descriptions = {
        'Равномерность плотности': 'Равномерность распределения точек по модели',
        'Анализ пустот и скоплений': 'Наличие выбросов и аномалий в распределении точек',
        'Несвязные компоненты': 'Количество разрозненных частей модели',
        'Дыры и самопересечения': 'Наличие отверстий, отсутствующих фрагментов поверхности и разрывов сетки',
        'Самопересечения': 'Факты пересечения элементов сетки друг с другом',
        'Замкнутость поверхности': 'Целостность и водонепроницаемость модели',
        'Равномерность площадей треугольников': 'Однородность размеров треугольников в сетке',
        'Регулярность нормалей': 'Согласованность направлений нормалей поверхности',
        'Структурная устойчивость': 'Отсутствие локальных искажений и артефактов'
    };
    return descriptions[key] || '';
}

function getQualityLevel(score) {
    if (score >= 0.8) return 'good';
    if (score >= 0.5) return 'medium';
    return 'poor';
}

function getQualityText(quality) {
    const texts = {
        'good': 'Высокое',
        'medium': 'Среднее',
        'poor': 'Низкое'
    };
    return texts[quality] || quality;
}