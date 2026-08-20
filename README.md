# VanDrishti — Forest Intelligence Platform 🌲🛰️

**VanDrishti** (*"Forest Vision"*) is an AI-powered geospatial intelligence and field verification platform designed for automated forest monitoring, individual tree crown detection, canopy degradation analysis, thermal fire hotspot tracking, and terrain-aware ground patrol route optimization.

---

## 🌟 Key Capabilities

1. **Deep Learning Tree Crown Detection**
   - **DeepForest 2.1 & YOLOv8** model integration for high-resolution crown boundary prediction on **NEON Airborne Observation Platform (AOP)** 10 cm/pixel RGB orthomosaics and hyperspectral imagery.
   - Spatial Non-Maximum Suppression (NMS) and boundary-aware filtering.

2. **Multi-Factor Ground Verification Priority Engine**
   - Ranks tree audit priority into **HIGH**, **MEDIUM**, and **LOW** based on:
     - Direct impact within proposed infrastructure / linear project corridors.
     - Model prediction uncertainty (low-confidence tiers requiring ground truth verification).
     - Ecological sensitivity and proximity to degradation zones.

3. **Terrain-Aware Dijkstra Least-Cost Path (LCP) & Held-Karp TSP Routing**
   - Builds 8-connected grid graph over **Excess Green Index ($\text{ExG} = 2G - R - B$)** vegetation cost impedance surface.
   - Solves exact open-path **Traveling Salesperson Problem (TSP)** using **Held-Karp Dynamic Programming**, eliminating backtracking and directing field rangers through natural canopy gaps.

4. **NASA FIRMS Active Thermal Anomaly Monitoring**
   - Real-time ingestion of **VIIRS 375m NRT (S-NPP)** active fire detections with Fire Radiative Power (FRP) intensity and confidence scoring.

5. **Interactive GIS Dashboard (React + Leaflet)**
   - High-performance interactive map featuring real WGS84 GeoJSON spatial layers, satellite basemaps, live statistics, turn-by-turn verification itineraries, and feature inspection.

---

## 📁 Repository Structure

```
VanDrishti/
├── data/                       # Spatial dataset assets
│   ├── demo/                   # Demo boundary and reference polygons
│   ├── processed/yolo/         # YOLO annotations and tiles
│   └── raw/neon/               # NEON AOP aerial tiles and LiDAR data
├── frontend/                   # Interactive React GIS Dashboard
│   ├── public/data/            # WGS84 GeoJSON layers & clean map images
│   ├── src/
│   │   ├── App.jsx             # Main interactive dashboard component
│   │   ├── index.css           # Pure self-contained dark forest theme
│   │   └── main.jsx
│   └── package.json
├── results/                    # Generated GIS outputs & trained models
│   ├── gis/                    # GeoJSON routes, boundaries, priorities, and map visualizations
│   └── yolov8/                 # Model checkpoints & training logs
├── scripts/                    # Core Python pipeline modules
│   ├── run_pipeline_large_study_area.py   # Full 250m study area pipeline
│   ├── run_tsp_optimization_large.py      # Held-Karp TSP route optimizer
│   ├── generate_canopy_route_clean.py     # Clean 2-panel canopy mask visualizer
│   ├── reproject_frontend_data.py         # EPSG:32617 -> EPSG:4326 reprojection
│   ├── fire_detection_firms.py            # NASA FIRMS live fire fetcher
│   ├── degradation_change.py              # Multi-temporal ExG degradation analysis
│   └── train_yolov8.py                    # YOLOv8 fine-tuning script
└── README.md
```

---

## 🚀 Quickstart Guide

### 1. Python Geospatial Pipeline Setup

```bash
# Clone repository
git clone https://github.com/prathamkhanduja0-max/VanDrishti.git
cd VanDrishti

# Install dependencies
pip install numpy scipy pillow matplotlib shapely pyproj networkx pandas rasterio geopandas
```

### 2. Run the Full Detection & Routing Pipeline

```bash
# Run detection and priority engine for the 250m OSBS study area
python scripts/run_pipeline_large_study_area.py

# Run exact Held-Karp TSP optimization
python scripts/run_tsp_optimization_large.py

# Generate clean binary canopy mask and route map
python scripts/generate_canopy_route_clean.py

# Reproject GeoJSON layers to WGS84 for the frontend
python scripts/reproject_frontend_data.py
```

### 3. Launch Frontend Dashboard

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## 📊 Study Area Specifications

* **Site**: Ordway-Swisher Biological Station (OSBS), Putnam County, Florida (NEON Domain D03).
* **Primary Tile**: $250\text{m} \times 250\text{m}$ ($6.25\text{ ha}$) high-density canopy window.
* **Coordinate Systems**:
  * **Processing CRS**: UTM Zone 17N (`EPSG:32617`)
  * **Web GIS CRS**: WGS84 (`EPSG:4326`)
* **Tree Detections**: 684 verified canopies.
* **Audit Route**: 432.1 m optimal Dijkstra path across 13 high-priority validation stops.

---

## 📜 License

This project is licensed under the MIT License.
