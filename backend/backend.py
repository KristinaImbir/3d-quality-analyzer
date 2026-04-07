from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import trimesh
import tempfile
import os
from sklearn.neighbors import NearestNeighbors
import numpy as np
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="3D Model Quality Analyzer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# 3.1 ГЕОМЕТРИЧЕСКИЕ МЕТРИКИ
# ============================================================

def analyze_density_uniformity(mesh):
    """3.1.1 Равномерность плотности точек"""
    try:
        verts = mesh.vertices
        N = len(verts)

        if N < 10:
            return {
                'value': None,
                'normalized': None,
                'description': 'Недостаточно точек для анализа',
                'details': {}
            }

        # Определение k (3.2)
        k_density = int(np.clip(np.sqrt(N), 10, 30))

        nbrs = NearestNeighbors(n_neighbors=k_density + 1).fit(verts)
        distances, _ = nbrs.kneighbors(verts)

        # Rk(pi) - расстояние до k-го соседа
        rk = distances[:, -1] + 1e-10

        # Vi = 4/3 * π * Rk^3 (3.3)
        volumes = (4 / 3) * np.pi * (rk ** 3)

        # ρi = k / Vi (3.4)
        rho = k_density / volumes

        # Робастный коэффициент вариации (3.6-3.8)
        median_rho = np.median(rho)
        mad_rho = np.median(np.abs(rho - median_rho))
        cv_rob = mad_rho / (median_rho + 1e-10)

        # Q_density = e^{-CV_rob} (3.9)
        q_density = np.exp(-cv_rob)

        # Интерпретация
        if q_density >= 0.8:
            interpretation = "Высокая равномерность распределения точек"
        elif q_density >= 0.5:
            interpretation = "Средняя равномерность распределения точек"
        else:
            interpretation = "Низкая равномерность распределения точек"

        return {
            'value': float(cv_rob),
            'normalized': float(np.clip(q_density, 0, 1)),
            'description': 'Робастный коэффициент вариации локальных плотностей',
            'interpretation': interpretation,
            'parameters': {'k': k_density}
        }
    except Exception as e:
        logger.error(f"Ошибка в 3.1.1: {e}")
        return {
            'value': None,
            'normalized': None,
            'description': f'Ошибка: {str(e)}',
            'details': {}
        }


def analyze_voids_and_clusters(mesh):
    """3.1.2 Анализ пустот и скоплений"""
    try:
        verts = mesh.vertices
        N = len(verts)

        if N < 10:
            return {
                'value': None,
                'normalized': None,
                'description': 'Недостаточно точек для анализа',
                'details': {}
            }

        alpha = 2.5  # Коэффициент порога (3.13)

        # Расстояние до ближайшего соседа (3.10)
        nbrs_1 = NearestNeighbors(n_neighbors=2).fit(verts)
        dist_1, _ = nbrs_1.kneighbors(verts)
        di = dist_1[:, 1]  # d_i

        # Медианное расстояние (3.12)
        d_tilde = np.median(di)

        # Пустоты: d_i > α * d_tilde (3.13)
        void_mask = di > (alpha * d_tilde)
        n_void = np.sum(void_mask)
        r_void = n_void / N  # (3.14)

        # Скопления: d_i < (1/α) * d_tilde (аномально малые расстояния)
        cluster_mask = di < (d_tilde / alpha)
        n_cluster = np.sum(cluster_mask)
        r_cluster = n_cluster / N

        # Композитная оценка (учёт обоих типов аномалий)
        r_anomaly = (n_void + n_cluster) / N
        q_anomaly = 1.0 - r_anomaly  # (3.15)

        # Интерпретация
        if q_anomaly >= 0.8:
            interpretation = "Мало аномалий в распределении точек"
        elif q_anomaly >= 0.5:
            interpretation = "Среднее количество аномалий"
        else:
            interpretation = "Много аномалий (пустоты/скопления)"

        return {
            'value': float(r_anomaly),
            'normalized': float(np.clip(q_anomaly, 0, 1)),
            'description': 'Доля аномальных точек (пустоты и скопления)',
            'interpretation': interpretation,
            'details': {
                'alpha': alpha,
                'd_median': float(d_tilde),
                'void_ratio': float(r_void),
                'cluster_ratio': float(r_cluster),
                'N_void': int(n_void),
                'N_cluster': int(n_cluster)
            }
        }
    except Exception as e:
        logger.error(f"Ошибка в 3.1.2: {e}")
        return {
            'value': None,
            'normalized': None,
            'description': f'Ошибка: {str(e)}',
            'details': {}
        }


# ============================================================
# 3.2 ТОПОЛОГИЧЕСКИЕ МЕТРИКИ
# ============================================================

def analyze_watertight(mesh):
    """3.2.1 Замкнутость поверхности"""
    try:
        # Базовая проверка водонепроницаемости
        is_watertight = mesh.is_watertight

        # Количество граничных рёбер
        if hasattr(mesh, 'edges_boundary') and mesh.edges_boundary is not None:
            N_boundary = len(mesh.edges_boundary)
        else:
            if hasattr(mesh, 'face_adjacency'):
                all_edges = mesh.edges
                interior_edges = set(map(tuple, mesh.face_adjacency_edges))

                N_boundary = 0
                for edge in all_edges:
                    edge_tuple = tuple(sorted(edge))
                    if edge_tuple not in interior_edges:
                        N_boundary += 1
            else:
                if is_watertight:
                    N_boundary = 0
                else:
                    N_boundary = len(mesh.edges) // 10

        # Общее количество рёбер
        N_edges = len(mesh.edges) if hasattr(mesh, 'edges') else 0

        # Отношение граничных рёбер (3.18)
        if N_edges > 0:
            R_boundary = N_boundary / N_edges
        else:
            R_boundary = 1.0

        # Нормированная оценка (3.19)
        Q_closed = 1.0 - R_boundary

        # Для водонепроницаемых моделей всегда даём высокую оценку
        if is_watertight:
            normalized_score = 1.0
        else:
            normalized_score = Q_closed

        return {
            'value': bool(is_watertight),
            'normalized': float(np.clip(normalized_score, 0, 1)),
            'description': 'Замкнутость поверхности (доля внутренних рёбер)',
            'details': {
                'is_watertight': is_watertight,
                'boundary_edges': int(N_boundary),
                'total_edges': int(N_edges),
                'R_boundary': float(R_boundary)
            }
        }
    except Exception as e:
        logger.error(f"Ошибка в 3.2.1: {e}")
        return {
            'value': None,
            'normalized': None,
            'description': f'Ошибка: {str(e)}',
            'details': {}
        }


def analyze_components(mesh):
    """3.2.2 Количество несвязных компонент (через граф рёбер)"""
    try:
        # Проверяем наличие граней
        if not hasattr(mesh, 'faces') or len(mesh.faces) == 0:
            return {
                'value': None,
                'normalized': None,
                'description': 'Модель не содержит граней (облако точек)',
                'details': {}
            }

        # Получаем уникальные рёбра
        edges = mesh.edges_unique

        if len(edges) == 0:
            return {
                'value': len(mesh.vertices),
                'normalized': 0.0,
                'description': 'Нет рёбер (изолированные вершины)',
                'details': {'components_count': len(mesh.vertices)}
            }

        # Строим граф связности через рёбра
        adjacency = {}

        for edge in edges:
            v1, v2 = edge
            adjacency.setdefault(v1, set()).add(v2)
            adjacency.setdefault(v2, set()).add(v1)

        all_vertices = set(adjacency.keys())

        # DFS для поиска компонент
        def dfs(start, visited):
            stack = [start]
            component = []
            while stack:
                vertex = stack.pop()
                if vertex not in visited:
                    visited.add(vertex)
                    component.append(vertex)
                    for neighbor in adjacency.get(vertex, []):
                        if neighbor not in visited:
                            stack.append(neighbor)
            return component

        visited = set()
        components = []

        for vertex in all_vertices:
            if vertex not in visited:
                component = dfs(vertex, visited)
                components.append(component)

        C = len(components)

        # Анализ размеров компонент
        component_sizes = [len(comp) for comp in components]
        component_sizes.sort(reverse=True)

        # Доля главной компоненты
        if component_sizes:
            main_ratio = component_sizes[0] / sum(component_sizes)
        else:
            main_ratio = 0.0

        # Нормированная оценка (3.21) — используем долю главной компоненты
        Q_comp = main_ratio

        interpretation = f"{C} компонент, главная: {main_ratio:.1%}"
        if C > 1:
            interpretation += f", остальные: {component_sizes[1:5]}..."

        return {
            'value': int(C),
            'normalized': float(np.clip(Q_comp, 0, 1)),
            'description': 'Доля главной связной компоненты',
            'interpretation': interpretation,
            'details': {
                'components_count': C,
                'component_sizes': component_sizes[:10],
                'main_component_ratio': float(main_ratio),
                'main_component_size': int(component_sizes[0]) if component_sizes else 0,
                'total_vertices': len(all_vertices)
            }
        }

    except Exception as e:
        logger.error(f"Ошибка в 3.2.2: {e}")
        return {
            'value': None,
            'normalized': None,
            'description': f'Ошибка: {str(e)}',
            'details': {}
        }


def analyze_holes_and_intersections(mesh, components_count=1):
    """3.2.3 Наличие дыр и самопересечений с учётом компонент"""
    try:
        # Дыры (отверстия)
        N_holes = 0
        if hasattr(mesh, 'boundary_loops'):
            N_holes = len(mesh.boundary_loops)
        elif hasattr(mesh, 'edges_boundary'):
            try:
                from trimesh import grouping
                if hasattr(mesh, 'edges_boundary'):
                    boundary_edges = mesh.edges[mesh.edges_boundary]
                    if len(boundary_edges) > 0:
                        boundary_groups = grouping.group_rows(boundary_edges, require_count=1)
                        N_holes = len(boundary_groups)
            except:
                N_holes = 0

        # Самопересечения
        has_self_intersections = False
        if hasattr(mesh, 'is_self_intersecting'):
            try:
                has_self_intersections = mesh.is_self_intersecting
            except:
                has_self_intersections = False

        N_inter = 1 if has_self_intersections else 0

        # Штраф за множество компонент
        component_penalty = 0
        if components_count > 1:
            component_penalty = min(0.5, (components_count - 1) * 0.05)

        # Общее количество дефектов (3.22) с учётом штрафа
        N_def = N_inter + N_holes + component_penalty

        # Нормированная оценка (3.23)
        Q_topo = 1.0 / (1.0 + N_def)

        # Интерпретация
        if components_count == 1 and N_holes == 0 and not has_self_intersections:
            interpretation = "Нет дыр, самопересечений и лишних компонент"
        elif components_count > 1:
            interpretation = f"{components_count} компонент, {N_holes} отверстий, штраф {component_penalty:.2f}"
        elif N_holes > 0 and not has_self_intersections:
            interpretation = f"{N_holes} отверстий, нет самопересечений"
        elif not N_holes > 0 and has_self_intersections:
            interpretation = "Есть самопересечения, нет отверстий"
        else:
            interpretation = f"{N_holes} отверстий, есть самопересечения"

        return {
            'value': int(N_holes + N_inter),
            'normalized': float(np.clip(Q_topo, 0, 1)),
            'description': 'Наличие топологических дефектов (с учётом компонент)',
            'interpretation': interpretation,
            'details': {
                'holes': int(N_holes),
                'has_self_intersections': bool(has_self_intersections),
                'components_count': components_count,
                'component_penalty': float(component_penalty),
                'total_defects_value': float(N_def)
            }
        }
    except Exception as e:
        logger.error(f"Ошибка в 3.2.3: {e}")
        return {
            'value': None,
            'normalized': None,
            'description': f'Ошибка: {str(e)}',
            'details': {}
        }


def analyze_triangle_area_uniformity(mesh):
    """3.3.1 Равномерность площадей треугольников"""
    try:
        # Проверяем наличие граней
        if not hasattr(mesh, 'faces') or len(mesh.faces) == 0:
            return {
                'value': None,
                'normalized': None,
                'description': 'Модель не содержит граней',
                'details': {}
            }

        vertices = mesh.vertices
        faces = mesh.faces

        # Вычисляем площади всех треугольников (3.25)
        areas = []
        for face in faces:
            v1 = vertices[face[0]]
            v2 = vertices[face[1]]
            v3 = vertices[face[2]]

            cross = np.cross(v2 - v1, v3 - v1)
            area = 0.5 * np.linalg.norm(cross)
            areas.append(area)

        areas = np.array(areas)

        # Робастная оценка (3.27-3.29)
        median_area = np.median(areas)
        mad_area = np.median(np.abs(areas - median_area))

        # Защита от деления на ноль
        if median_area < 1e-10:
            cv_rob = 1.0
        else:
            cv_rob = mad_area / median_area

        # Нормированная оценка (3.30)
        Q_area = np.exp(-cv_rob)

        # Интерпретация
        if Q_area >= 0.8:
            interpretation = "Триангуляция равномерная"
        elif Q_area >= 0.5:
            interpretation = "Средняя равномерность триангуляции"
        else:
            interpretation = "Сильный разброс площадей треугольников"

        return {
            'value': float(cv_rob),
            'normalized': float(np.clip(Q_area, 0, 1)),
            'description': 'Однородность размеров треугольников в сетке',
            'interpretation': interpretation,
            'details': {
                'median_area': float(median_area),
                'mad_area': float(mad_area),
                'cv_rob': float(cv_rob),
                'total_faces': len(faces)
            }
        }
    except Exception as e:
        logger.error(f"Ошибка в 3.3.1: {e}")
        return {
            'value': None,
            'normalized': None,
            'description': f'Ошибка: {str(e)}',
            'details': {}
        }


def analyze_normal_regularity(mesh):
    """3.3.2 Регулярность нормалей"""
    try:
        # Проверяем наличие граней
        if not hasattr(mesh, 'faces') or len(mesh.faces) == 0:
            return {
                'value': None,
                'normalized': None,
                'description': 'Модель не содержит граней',
                'details': {}
            }

        if hasattr(mesh, 'face_normals') and len(mesh.face_normals) > 0:
            face_normals = mesh.face_normals
        else:
            vertices = mesh.vertices
            faces = mesh.faces
            face_normals = []
            for face in faces:
                v1 = vertices[face[0]]
                v2 = vertices[face[1]]
                v3 = vertices[face[2]]
                normal = np.cross(v2 - v1, v3 - v1)
                norm = np.linalg.norm(normal)
                if norm > 0:
                    normal = normal / norm
                face_normals.append(normal)
            face_normals = np.array(face_normals)

        if not hasattr(mesh, 'face_adjacency') or len(mesh.face_adjacency) == 0:
            return {
                'value': None,
                'normalized': None,
                'description': 'Нет информации о соседних гранях',
                'details': {}
            }

        # Вычисляем углы между нормалями соседних граней (3.32)
        angles = []
        for face_pair in mesh.face_adjacency:
            i, j = face_pair
            n_i = face_normals[i]
            n_j = face_normals[j]

            dot = np.clip(np.dot(n_i, n_j), -1.0, 1.0)
            angle = np.arccos(dot)
            angles.append(angle)

        angles = np.array(angles)

        # Медианный угол (3.34)
        median_angle = np.median(angles)

        # Нормированная оценка (3.35)
        Q_norm = np.exp(-median_angle)

        # Интерпретация
        if median_angle < 0.2:  # ~11 градусов
            interpretation = "Поверхность гладкая"
        elif median_angle < 0.5:  # ~28 градусов
            interpretation = "Средняя гладкость поверхности"
        else:
            interpretation = "Поверхность имеет изломы/артефакты"

        return {
            'value': float(median_angle),
            'normalized': float(np.clip(Q_norm, 0, 1)),
            'description': 'Согласованность направлений нормалей поверхности',
            'interpretation': interpretation,
            'details': {
                'median_angle_rad': float(median_angle),
                'median_angle_deg': float(np.degrees(median_angle)),
                'total_adjacent_pairs': len(angles)
            }
        }
    except Exception as e:
        logger.error(f"Ошибка в 3.3.2: {e}")
        return {
            'value': None,
            'normalized': None,
            'description': f'Ошибка: {str(e)}',
            'details': {}
        }


def analyze_structural_stability(mesh):
    """3.3.3 Структурная устойчивость"""
    try:
        verts = mesh.vertices
        N = len(verts)

        if N < 10:
            return {
                'value': None,
                'normalized': None,
                'description': 'Недостаточно точек для анализа',
                'details': {}
            }

        # Определяем k (аналогично 3.1.1)
        k_stab = int(np.clip(np.sqrt(N), 10, 30))

        # Расстояния до k ближайших соседей
        nbrs = NearestNeighbors(n_neighbors=k_stab + 1).fit(verts)
        distances, _ = nbrs.kneighbors(verts)

        # Среднее расстояние до k ближайших соседей (3.36)
        mean_distances = np.mean(distances[:, 1:k_stab + 1], axis=1)

        # Робастная оценка (3.38-3.40)
        median_dist = np.median(mean_distances)
        mad_dist = np.median(np.abs(mean_distances - median_dist))

        # Защита от деления на ноль
        if median_dist < 1e-10:
            cv_rob = 1.0
        else:
            cv_rob = mad_dist / median_dist

        # Нормированная оценка (3.41)
        Q_stab = np.exp(-cv_rob)

        # Интерпретация
        if Q_stab >= 0.8:
            interpretation = "Высокая структурная устойчивость"
        elif Q_stab >= 0.5:
            interpretation = "Средняя структурная устойчивость"
        else:
            interpretation = "Низкая устойчивость, есть локальные искажения"

        return {
            'value': float(cv_rob),
            'normalized': float(np.clip(Q_stab, 0, 1)),
            'description': 'Отсутствие локальных искажений и артефактов',
            'interpretation': interpretation,
            'details': {
                'k': k_stab,
                'median_distance': float(median_dist),
                'mad_distance': float(mad_dist),
                'cv_rob': float(cv_rob)
            }
        }
    except Exception as e:
        logger.error(f"Ошибка в 3.3.3: {e}")
        return {
            'value': None,
            'normalized': None,
            'description': f'Ошибка: {str(e)}',
            'details': {}
        }


def analyze_with_trimesh(file_path: str):
    """Анализ 3D модели (геометрические метрики 3.1)"""
    try:
        mesh = trimesh.load(file_path)

        if mesh.is_empty:
            raise Exception("Модель пустая или не может быть загружена")

        # ========== ДИАГНОСТИКА ==========
        print(f"=== ДИАГНОСТИКА МОДЕЛИ ===")
        print(f"Вершин: {len(mesh.vertices)}")
        print(f"Граней: {len(mesh.faces) if hasattr(mesh, 'faces') else 0}")
        print(f"Рёбер: {len(mesh.edges) if hasattr(mesh, 'edges') else 0}")
        print(f"is_watertight: {mesh.is_watertight if hasattr(mesh, 'is_watertight') else 'N/A'}")

        if hasattr(mesh, 'faces') and len(mesh.faces) > 0:
            print(f"Первые 5 граней: {mesh.faces[:5]}")
        else:
            print("ВНИМАНИЕ: У модели нет граней! Только вершины.")
        print(f"==========================")
        # ========== КОНЕЦ ДИАГНОСТИКИ ==========

        metrics = {}

        # --- Базовая информация ---
        bbox = mesh.bounding_box
        try:
            bbox_volume = float(bbox.volume)
        except Exception:
            bbox_volume = float(mesh.convex_hull.volume) if hasattr(mesh.convex_hull, 'volume') else 0.0

        metrics['basic_info'] = {
            'vertices': int(len(mesh.vertices)),
            'faces': int(len(mesh.faces)) if hasattr(mesh, 'faces') else 0,
            'volume': bbox_volume
        }

        # ============================================================
        # 3.1 ГЕОМЕТРИЧЕСКИЕ МЕТРИКИ
        # ============================================================

        # 3.1.1 Равномерность плотности точек
        metrics['Равномерность плотности'] = analyze_density_uniformity(mesh)

        # 3.1.2 Анализ пустот и скоплений
        metrics['Анализ пустот и скоплений'] = analyze_voids_and_clusters(mesh)

        # ============================================================
        # 3.2 ТОПОЛОГИЧЕСКИЕ МЕТРИКИ
        # ============================================================

        # 3.2.1 Замкнутость поверхности
        metrics['Замкнутость поверхности'] = analyze_watertight(mesh)

        # 3.2.2 Количество несвязных компонент
        components_result = analyze_components(mesh)
        metrics['Несвязные компоненты'] = components_result

        # Получаем количество компонент для штрафа
        components_count = components_result.get('value', 1) if components_result else 1

        # 3.2.3 Наличие дыр и самопересечений (с передачей количества компонент)
        metrics['Дыры и самопересечения'] = analyze_holes_and_intersections(mesh, components_count)

        # ============================================================
        # 3.3 СТРУКТУРНЫЕ МЕТРИКИ
        # ============================================================

        # 3.3.1 Равномерность площадей треугольников
        metrics['Равномерность площадей треугольников'] = analyze_triangle_area_uniformity(mesh)

        # 3.3.2 Регулярность нормалей
        metrics['Регулярность нормалей'] = analyze_normal_regularity(mesh)

        # 3.3.3 Структурная устойчивость
        metrics['Структурная устойчивость'] = analyze_structural_stability(mesh)

        return metrics

    except Exception as e:
        raise Exception(f"Ошибка анализа: {str(e)}")


def calculate_overall_score(metrics):
    """3.4 Обобщённая метрика качества (агрегирование по категориям)"""

    category_metrics = {
        'geometric': ['Равномерность плотности', 'Анализ пустот и скоплений'],
        'topological': ['Замкнутость поверхности', 'Несвязные компоненты', 'Дыры и самопересечения'],
        'structural': ['Равномерность площадей треугольников', 'Регулярность нормалей', 'Структурная устойчивость']
    }

    category_scores = {}

    for category, metric_names in category_metrics.items():
        valid_scores = []
        for metric_name in metric_names:
            if metric_name in metrics:
                metric = metrics[metric_name]
                if isinstance(metric, dict) and 'normalized' in metric and metric['normalized'] is not None:
                    valid_scores.append(metric['normalized'])

        if valid_scores:
            # Среднее по категории (3.44-3.46)
            category_scores[category] = sum(valid_scores) / len(valid_scores)
        else:
            category_scores[category] = None

    # Итоговая оценка как среднее по категориям (3.47)
    valid_category_scores = [score for score in category_scores.values() if score is not None]

    if valid_category_scores:
        overall_score = sum(valid_category_scores) / len(valid_category_scores)
    else:
        overall_score = None

    return {
        'overall_score': overall_score,
        'category_scores': category_scores,
        'method': 'Агрегирование по категориям (3.44-3.47)'
    }


@app.post("/api/analyze")
async def analyze_model(file: UploadFile = File(...)):
    tmp_path = None
    try:
        logger.info(f"Начало анализа файла: {file.filename}")
        print(f"Анализируем файл: {file.filename}")

        suffix = os.path.splitext(file.filename)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_path = tmp_file.name

        metrics = analyze_with_trimesh(tmp_path)

        # ========== ОБОБЩЁННАЯ МЕТРИКА (3.4) ==========
        overall_result = calculate_overall_score(metrics)
        overall_score = overall_result['overall_score']
        # ====================================================

        response = {
            'success': True,
            'metrics': metrics,
            'overall_score': overall_score,
            'category_scores': overall_result['category_scores'],
            'filename': file.filename
        }

        return JSONResponse(response)

    except Exception as e:
        print(f"Ошибка: {str(e)}")
        return JSONResponse({
            'success': False,
            'error': str(e)
        }, status_code=500)

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.get("/")
async def root():
    return {"message": "3D Model Quality Analyzer API"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
