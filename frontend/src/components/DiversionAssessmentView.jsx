/**
 * DiversionAssessmentView.jsx -- VanDrishti Forest Diversion Assessment Component
 * Displays publication-ready 13-section forest diversion assessment dashboard.
 * 100% Data-Driven & Site-Aware with Data Provenance & Freshness Badges.
 */

import React, { useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  Download,
  FileText,
  Flame,
  Info,
  Layers,
  Navigation,
  Printer,
  RefreshCw,
  Scissors,
  ShieldAlert,
  ShieldCheck,
  Trees,
} from 'lucide-react';
import { apiService } from '../services/api';
import './DiversionAssessmentView.css';

export function DiversionAssessmentView({ currentSite = 'OSBS_large_2019' }) {
  const [assessment, setAssessment] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [priorityFilter, setPriorityFilter] = useState('ALL');

  // Pagination State
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 25;

  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true);
        setError(null);
        const data = await apiService.getDiversionAssessment(currentSite);
        if (data) {
          setAssessment(data);
        }
        setLoading(false);
      } catch (err) {
        console.error('Failed loading diversion assessment payload:', err);
        setError(err.message);
        setLoading(false);
      }
    }
    loadData();
    setCurrentPage(1);
  }, [currentSite]);

  const triggerDownload = (url) => {
    const a = document.createElement('a');
    a.href = url;
    a.download = '';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const handleDownloadPDF = () => {
    const encoded = encodeURIComponent(currentSite);
    triggerDownload(`/api/diversion/export/pdf?site=${encoded}`);
  };

  const handleDownloadCSV = () => {
    const encoded = encodeURIComponent(currentSite);
    triggerDownload(`/api/diversion/export/csv?site=${encoded}`);
  };

  const handlePrint = () => {
    window.print();
  };

  if (loading) {
    return (
      <div className="diversion-container" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <RefreshCw size={24} style={{ animation: 'spin 1s linear infinite', color: '#34d399' }} />
        <div style={{ marginTop: '12px', fontSize: '13px', color: '#94a3b8' }}>
          Compiling Site-Specific Forest Diversion Assessment for '{currentSite}'...
        </div>
      </div>
    );
  }

  if (error || !assessment) {
    return (
      <div className="diversion-container" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <AlertTriangle size={28} style={{ color: '#ef4444' }} />
        <div style={{ marginTop: '12px', fontSize: '14px', color: '#f87171', fontWeight: 600 }}>
          Failed to Load Diversion Assessment
        </div>
        <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '4px' }}>
          {error || 'No assessment data returned for this site context.'}
        </div>
      </div>
    );
  }

  const summary = assessment.summary || {};
  const siteCtx = assessment.site_context || {};
  const provenance = assessment.provenance || {};
  const capabilities = assessment.capabilities || {};
  const inventory = assessment.inventory_sample || [];

  const filteredInventory = inventory.filter((item) => {
    const matchesSearch = searchQuery === '' ||
      item.tree_id.toString().includes(searchQuery) ||
      item.rationale.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesPriority = priorityFilter === 'ALL' || item.priority === priorityFilter;
    return matchesSearch && matchesPriority;
  });

  const totalPages = Math.max(1, Math.ceil(filteredInventory.length / pageSize));
  const startIndex = (currentPage - 1) * pageSize;
  const paginatedInventory = filteredInventory.slice(startIndex, startIndex + pageSize);

  return (
    <div className="diversion-container">
      {/* 1. HEADER ACTION BAR & SITE CONTEXT */}
      <div className="diversion-header-bar">
        <div className="diversion-title-group">
          <div className="diversion-badge-icon">
            <ShieldCheck size={24} />
          </div>
          <div>
            <div className="diversion-doc-title">Site-Specific Forest Diversion Assessment</div>
            <div className="diversion-doc-sub">
              {siteCtx.site_name} • {siteCtx.study_tile_label} • Generated: {siteCtx.generated_at}
            </div>
          </div>
        </div>

        <div className="diversion-actions">
          <button onClick={handleDownloadPDF} className="btn-export pdf" title="Export Publication-Ready PDF Report">
            <FileText size={14} />
            <span>Download PDF Report</span>
          </button>
          <button onClick={handleDownloadCSV} className="btn-export csv" title="Export Tree Inventory CSV">
            <Download size={14} />
            <span>Export Inventory CSV</span>
          </button>
          <button onClick={handlePrint} className="btn-export csv" title="Print Evidence Summary">
            <Printer size={14} />
            <span>Print Summary</span>
          </button>
        </div>
      </div>

      {/* 2. STATUTORY DECISION SUPPORT NOTICE */}
      <div className="diversion-notice-banner">
        <ShieldAlert size={18} style={{ color: '#ef4444', flexShrink: 0, marginTop: '2px' }} />
        <div>
          <div style={{ fontWeight: 700, color: '#f87171', marginBottom: '2px' }}>
            Statutory Decision Support & Spatial Evidence Disclaimer
          </div>
          <div>
            This assessment provides spatial, ecological, and mathematical verification data for field officers and statutory authorities.
            It evaluates proposed right-of-way corridor impact without replacing formal statutory environmental clearances.
          </div>
        </div>
      </div>

      {/* 3. DATA PROVENANCE & FRESHNESS MATRIX PANEL */}
      <div className="diversion-section">
        <div className="section-header">
          <Clock size={16} />
          <span>Data Provenance & Acquisition Freshness Matrix</span>
        </div>
        <div className="section-body">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '10px' }}>
            <div className="prov-tile">
              <div className="prov-label">RGB Canopy Detection</div>
              <div className="prov-value">{provenance.tree_detection?.source}</div>
              <div className="prov-tag historical">{provenance.tree_detection?.freshness}</div>
            </div>
            <div className="prov-tile">
              <div className="prov-label">LiDAR Structural Validation</div>
              <div className="prov-value">{provenance.lidar_validation?.source}</div>
              <div className="prov-tag historical">{provenance.lidar_validation?.freshness}</div>
            </div>
            <div className="prov-tile">
              <div className="prov-label">Forest Health Composite</div>
              <div className="prov-value">{provenance.health_grid?.source}</div>
              <div className="prov-tag historical">{provenance.health_grid?.freshness}</div>
            </div>
            <div className="prov-tile">
              <div className="prov-label">NASA FIRMS Thermal Fire</div>
              <div className="prov-value">{provenance.fire_monitoring?.source}</div>
              <div className="prov-tag live">{provenance.fire_monitoring?.freshness}</div>
            </div>
          </div>
        </div>
      </div>

      {/* 4. TOP KPI IMPACT CARDS */}
      <div className="diversion-kpi-grid">
        <div className="kpi-card">
          <div className="kpi-label">Corridor Canopy Impact</div>
          <div className="kpi-value" style={{ color: '#f87171' }}>
            {summary.impacted_trees_count} <span className="kpi-sub">trees ({summary.impacted_pct}%)</span>
          </div>
          <div className="kpi-sub">
            Out of {summary.operational_inventory_count?.toLocaleString()} operational inventory trees
          </div>
          <div className="provenance-tag">
            <Info size={10} /> Spatial GIS Intersection (60m Corridor)
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">Mandatory Audit Targets</div>
          <div className="kpi-value" style={{ color: '#fbbf24' }}>
            {summary.high_priority_count} <span className="kpi-sub">HIGH Priority</span>
          </div>
          <div className="kpi-sub">
            {summary.impacted_high_priority_count} inside corridor (low-tier confidence)
          </div>
          <div className="provenance-tag">
            <Info size={10} /> Rules-Based Priority Matrix
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">Forest Health Exposure</div>
          <div className="kpi-value" style={{ color: '#4ade80' }}>
            {summary.health_grade_a + summary.health_grade_b} <span className="kpi-sub">Grade A/B Cells</span>
          </div>
          <div className="kpi-sub">
            Total Grid: {summary.total_health_cells} cells ({capabilities.health_score || 'HISTORICAL'})
          </div>
          <div className="provenance-tag">
            <Info size={10} /> 25m Composite LiDAR Canopy Cover
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">Verification Traversal</div>
          <div className="kpi-value" style={{ color: '#22d3ee' }}>
            {summary.field_route_distance_m} <span className="kpi-sub">m ({summary.field_route_time_min} min)</span>
          </div>
          <div className="kpi-sub">
            Held-Karp TSP traversal across {summary.field_route_stops_count} audit stops
          </div>
          <div className="provenance-tag">
            <Info size={10} /> Tobler DTM Slope Dijkstra Path
          </div>
        </div>
      </div>

      {/* 5. TREE INVENTORY FUNNEL & QUALITY PIPELINE */}
      <div className="diversion-section">
        <div className="section-header">
          <Layers size={16} />
          <span>5. Data Population & Quality Pipeline Funnel</span>
        </div>
        <div className="section-body">
          <div style={{ fontSize: '11.5px', color: '#94a3b8', fontStyle: 'italic', marginBottom: '12px' }}>
            {assessment.funnel_explanation}
          </div>

          <table className="diversion-table">
            <thead>
              <tr>
                <th>Pipeline Stage</th>
                <th>Tree Count</th>
                <th>Description & Data Provenance</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><b>Raw Model Predictions</b></td>
                <td><b style={{ color: '#f1f5f9' }}>{summary.raw_trees_count?.toLocaleString()}</b></td>
                <td>DeepForest 2.1 RetinaNet Canopy Bounding Boxes (2019 RGB)</td>
              </tr>
              <tr>
                <td><b>LiDAR Validated Trees</b></td>
                <td><b style={{ color: '#38bdf8' }}>{summary.validated_trees_count?.toLocaleString()}</b></td>
                <td>Centroid height sampled against LiDAR CHM (filtered for height ≥ 2.0 m)</td>
              </tr>
              <tr>
                <td><b>Operational Inventory</b></td>
                <td><b style={{ color: '#6ee7b7' }}>{summary.operational_inventory_count?.toLocaleString()}</b></td>
                <td>Confidence ≥ 0.50 & spatial centroid deduplication</td>
              </tr>
              <tr style={{ background: 'rgba(239, 68, 68, 0.08)' }}>
                <td><b style={{ color: '#f87171' }}>Corridor-Impacted Trees</b></td>
                <td><b style={{ color: '#f87171' }}>{summary.impacted_trees_count?.toLocaleString()}</b></td>
                <td>Direct spatial intersection inside proposed project right-of-way corridor</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* 6. ECOLOGICAL PRIORITY MATRIX */}
      <div className="diversion-section">
        <div className="section-header">
          <AlertTriangle size={16} />
          <span>6. Ecological Verification Priority Matrix</span>
        </div>
        <div className="section-body">
          <table className="diversion-table">
            <thead>
              <tr>
                <th>Priority Rank</th>
                <th>Total Count</th>
                <th>Corridor Impacted</th>
                <th>Outside Buffer</th>
                <th>Ground Audit Protocol</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><span className="badge-priority high">HIGH</span></td>
                <td><b>{summary.high_priority_count}</b></td>
                <td><b style={{ color: '#f87171' }}>{summary.impacted_high_priority_count}</b></td>
                <td>{summary.high_priority_count - summary.impacted_high_priority_count}</td>
                <td>Mandatory ground truth audit (corridor impact & low-tier confidence)</td>
              </tr>
              <tr>
                <td><span className="badge-priority medium">MEDIUM</span></td>
                <td><b>{summary.medium_priority_count}</b></td>
                <td><b style={{ color: '#fbbf24' }}>{summary.impacted_medium_priority_count}</b></td>
                <td>{summary.medium_priority_count - summary.impacted_medium_priority_count}</td>
                <td>Statutory check (corridor impact with moderate confidence)</td>
              </tr>
              <tr>
                <td><span className="badge-priority low">LOW</span></td>
                <td><b>{summary.low_priority_count}</b></td>
                <td><b style={{ color: '#4ade80' }}>{summary.impacted_low_priority_count}</b></td>
                <td>{summary.low_priority_count - summary.impacted_low_priority_count}</td>
                <td>Safe buffer canopy outside proposed corridor</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* 7. HEALTH, DEGRADATION & THERMAL FIRE INTELLIGENCE */}
      <div className="diversion-section">
        <div className="section-header">
          <Activity size={16} />
          <span>7. Forest Health, Degradation & NASA FIRMS Thermal Fire Stream</span>
        </div>
        <div className="section-body">
          <table className="diversion-table">
            <thead>
              <tr>
                <th>Analytics Module</th>
                <th>Value / Count</th>
                <th>Capability Status</th>
                <th>Data Source & Freshness</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><b>Forest Health Grid</b></td>
                <td><b>{summary.total_health_cells} cells</b> (Grades A:{summary.health_grade_a}, B:{summary.health_grade_b}, C:{summary.health_grade_c}, D:{summary.health_grade_d})</td>
                <td><span className="prov-tag historical">{capabilities.health_score || 'HISTORICAL'}</span></td>
                <td>25m Composite Canopy Cover & Diversity (NEON 2018/2019)</td>
              </tr>
              <tr>
                <td><b>Canopy Loss Degradation</b></td>
                <td><b>{summary.total_degradation_polygons} zones</b> ({summary.degradation_removal_count} Removal, {summary.degradation_thinning_count} Thinning)</td>
                <td><span className="prov-tag historical">{capabilities.degradation || 'HISTORICAL'}</span></td>
                <td>Multi-Temporal LiDAR CHM Differencing (2018 vs 2019)</td>
              </tr>
              <tr>
                <td><b>NASA FIRMS Thermal Fire</b></td>
                <td><b>{summary.fire_hotspots_count} active hotspots</b></td>
                <td><span className="prov-tag live">{provenance.fire_monitoring?.status || 'LIVE_REAL_TIME'}</span></td>
                <td>{provenance.fire_monitoring?.source} ({provenance.fire_monitoring?.freshness})</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* 8. TREE-BY-TREE AUDIT INVENTORY WITH PAGINATION */}
      <div className="diversion-section">
        <div className="section-header" style={{ justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Trees size={16} />
            <span>8. Operational Tree Inventory ({filteredInventory.length} Filtered)</span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <input
              type="text"
              placeholder="Search Tree ID or Rationale..."
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setCurrentPage(1);
              }}
              style={{
                background: '#07130d',
                border: '1px solid #143624',
                borderRadius: '6px',
                padding: '4px 10px',
                fontSize: '11px',
                color: '#e2e8f0',
                outline: 'none',
              }}
            />
            <select
              value={priorityFilter}
              onChange={(e) => {
                setPriorityFilter(e.target.value);
                setCurrentPage(1);
              }}
              style={{
                background: '#07130d',
                border: '1px solid #143624',
                borderRadius: '6px',
                padding: '4px 8px',
                fontSize: '11px',
                color: '#e2e8f0',
                outline: 'none',
              }}
            >
              <option value="ALL">All Priorities</option>
              <option value="HIGH">HIGH Priority Only</option>
              <option value="MEDIUM">MEDIUM Priority Only</option>
              <option value="LOW">LOW Priority Only</option>
            </select>
          </div>
        </div>

        <div className="section-body">
          <table className="diversion-table">
            <thead>
              <tr>
                <th>Tree ID</th>
                <th>WGS84 Coordinates</th>
                <th>UTM Coordinates</th>
                <th>Confidence</th>
                <th>CHM Height</th>
                <th>Corridor</th>
                <th>Priority</th>
                <th>Audit Rationale</th>
              </tr>
            </thead>
            <tbody>
              {paginatedInventory.map((row) => (
                <tr key={row.tree_id}>
                  <td><b>#{row.tree_id}</b></td>
                  <td>{row.latitude.toFixed(5)}° N, {row.longitude.toFixed(5)}° W</td>
                  <td>E: {row.utm_easting.toFixed(1)}, N: {row.utm_northing.toFixed(1)}</td>
                  <td>{(row.confidence * 100).toFixed(1)}%</td>
                  <td>{row.chm_height_m} m</td>
                  <td>
                    <span style={{ color: row.corridor_status === 'INSIDE' ? '#f87171' : '#4ade80', fontWeight: 600 }}>
                      {row.corridor_status}
                    </span>
                  </td>
                  <td>
                    <span className={`badge-priority ${row.priority.toLowerCase()}`}>
                      {row.priority}
                    </span>
                  </td>
                  <td style={{ fontSize: '10.5px', color: '#94a3b8' }}>{row.rationale}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* PAGINATION CONTROLS */}
          <div className="pagination-bar">
            <span style={{ fontSize: '11px', color: '#94a3b8' }}>
              Showing {filteredInventory.length === 0 ? 0 : startIndex + 1} to {Math.min(startIndex + pageSize, filteredInventory.length)} of {filteredInventory.length} inventory records
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <button
                disabled={currentPage === 1}
                onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
                className="btn-page"
              >
                <ChevronLeft size={14} />
              </button>
              <span style={{ fontSize: '11px', color: '#e2e8f0', padding: '0 6px' }}>
                Page {currentPage} of {totalPages}
              </span>
              <button
                disabled={currentPage >= totalPages}
                onClick={() => setCurrentPage((prev) => Math.min(totalPages, prev + 1))}
                className="btn-page"
              >
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
