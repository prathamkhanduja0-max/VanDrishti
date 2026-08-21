/**
 * dijkstra.js -- VanDrishti Interactive Point-to-Point Pathfinding
 * Runs Dijkstra over an active 2D cost surface grid.
 */

// MinHeap for high performance Dijkstra priority queue
class MinHeap {
  constructor() {
    this.heap = [];
  }

  push(node) {
    this.heap.push(node);
    this._bubbleUp(this.heap.length - 1);
  }

  pop() {
    if (this.heap.length === 0) return null;
    const top = this.heap[0];
    const bottom = this.heap.pop();
    if (this.heap.length > 0) {
      this.heap[0] = bottom;
      this._bubbleDown(0);
    }
    return top;
  }

  isEmpty() {
    return this.heap.length === 0;
  }

  _bubbleUp(idx) {
    while (idx > 0) {
      const parentIdx = Math.floor((idx - 1) / 2);
      if (this.heap[idx].cost >= this.heap[parentIdx].cost) break;
      [this.heap[idx], this.heap[parentIdx]] = [this.heap[parentIdx], this.heap[idx]];
      idx = parentIdx;
    }
  }

  _bubbleDown(idx) {
    const len = this.heap.length;
    while (true) {
      let left = 2 * idx + 1;
      let right = 2 * idx + 2;
      let smallest = idx;

      if (left < len && this.heap[left].cost < this.heap[smallest].cost) {
        smallest = left;
      }
      if (right < len && this.heap[right].cost < this.heap[smallest].cost) {
        smallest = right;
      }
      if (smallest === idx) break;
      [this.heap[idx], this.heap[smallest]] = [this.heap[smallest], this.heap[idx]];
      idx = smallest;
    }
  }
}

/**
 * Solves Point-to-Point Dijkstra on a 2D cost surface
 * @param {Object} costSurface - Cost surface object containing grid, bounds, resolution, etc.
 * @param {Array} startLatLng - [lat, lon] of start point
 * @param {Array} endLatLng - [lat, lon] of end point
 * @returns {Object} Route result with GeoJSON, metrics, and term status
 */
export function computePointToPointPath(costSurface, startLatLng, endLatLng) {
  if (!costSurface || !costSurface.cost_grid) {
    throw new Error("No active cost surface loaded");
  }

  const grid = costSurface.cost_grid;
  const H = grid.length;
  const W = grid[0].length;
  const bounds = costSurface.wgs84_bounds; // [minLon, minLat, maxLon, maxLat]
  const [minLon, minLat, maxLon, maxLat] = bounds;

  // Convert lat/lon to grid row/col
  function latLngToGrid(lat, lon) {
    const col = Math.round(((lon - minLon) / (maxLon - minLon)) * (W - 1));
    const row = Math.round(((maxLat - lat) / (maxLat - minLat)) * (H - 1));
    return [
      Math.max(0, Math.min(H - 1, row)),
      Math.max(0, Math.min(W - 1, col)),
    ];
  }

  // Convert grid row/col to lat/lon
  function gridToLatLng(row, col) {
    const lon = minLon + ((col + 0.5) / W) * (maxLon - minLon);
    const lat = maxLat - ((row + 0.5) / H) * (maxLat - minLat);
    return [lat, lon];
  }

  const [startRow, startCol] = latLngToGrid(startLatLng[0], startLatLng[1]);
  const [endRow, endCol] = latLngToGrid(endLatLng[0], endLatLng[1]);

  // Dijkstra distances and parent pointers
  const dist = new Float32Array(H * W).fill(Infinity);
  const parent = new Int32Array(H * W).fill(-1);
  const visited = new Uint8Array(H * W).fill(0);

  const startIdx = startRow * W + startCol;
  const endIdx = endRow * W + endCol;

  dist[startIdx] = 0;
  const pq = new MinHeap();
  pq.push({ idx: startIdx, cost: 0 });

  // 8-connected neighbor offsets: [dRow, dCol, distMultiplier]
  const SQRT2 = Math.SQRT2;
  const neighbors = [
    [-1, 0, 1.0],
    [1, 0, 1.0],
    [0, -1, 1.0],
    [0, 1, 1.0],
    [-1, -1, SQRT2],
    [-1, 1, SQRT2],
    [1, -1, SQRT2],
    [1, 1, SQRT2],
  ];

  let reached = false;

  while (!pq.isEmpty()) {
    const current = pq.pop();
    const currIdx = current.idx;

    if (visited[currIdx]) continue;
    visited[currIdx] = 1;

    if (currIdx === endIdx) {
      reached = true;
      break;
    }

    const r = Math.floor(currIdx / W);
    const c = currIdx % W;
    const currCost = grid[r][c];

    for (let i = 0; i < 8; i++) {
      const nr = r + neighbors[i][0];
      const nc = c + neighbors[i][1];

      if (nr >= 0 && nr < H && nc >= 0 && nc < W) {
        const nextIdx = nr * W + nc;
        if (visited[nextIdx]) continue;

        const nextCost = grid[nr][nc];
        const stepDist = neighbors[i][2];
        const edgeWeight = ((currCost + nextCost) / 2.0) * stepDist;
        const newDist = dist[currIdx] + edgeWeight;

        if (newDist < dist[nextIdx]) {
          dist[nextIdx] = newDist;
          parent[nextIdx] = currIdx;
          pq.push({ idx: nextIdx, cost: newDist });
        }
      }
    }
  }

  if (!reached && dist[endIdx] === Infinity) {
    throw new Error("No valid path found between points");
  }

  // Reconstruct path
  const pathCoordinates = [];
  let curr = endIdx;
  let totalStepsPx = 0;
  let totalDistanceMetres = 0;
  let totalMinutes = 0;

  const resM = costSurface.res_m || 1.0;
  const isProjected = Boolean(costSurface.is_projected);
  const modeLabel = costSurface.mode_label || "canopy-aware (ExG proxy)";
  const isTerrainAware = modeLabel.includes("terrain");

  while (curr !== -1) {
    const r = Math.floor(curr / W);
    const c = curr % W;
    const [lat, lon] = gridToLatLng(r, c);
    pathCoordinates.push([lon, lat]); // GeoJSON is [lon, lat]

    const prev = parent[curr];
    if (prev !== -1) {
      const pr = Math.floor(prev / W);
      const pc = prev % W;
      const stepMult = (pr !== r && pc !== c) ? SQRT2 : 1.0;
      totalStepsPx += stepMult;

      if (isProjected && typeof resM === 'number') {
        const stepM = resM * stepMult;
        totalDistanceMetres += stepM;

        if (isTerrainAware) {
          // grid cost is in hours-per-km for Tobler
          const avgCost = (grid[r][c] + grid[pr][pc]) / 2.0;
          totalMinutes += avgCost * (stepM / 1000.0) * 60.0;
        } else {
          // ExG fallback at standard 4.0 km/h walking speed
          const avgExg = (grid[r][c] + grid[pr][pc]) / 2.0;
          const speedMpm = 66.7 / avgExg;
          totalMinutes += stepM / speedMpm;
        }
      }
    }

    if (curr === startIdx) break;
    curr = prev;
  }

  pathCoordinates.reverse();

  // Create GeoJSON Feature
  const geojson = {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        geometry: {
          type: "LineString",
          coordinates: pathCoordinates,
        },
        properties: {
          type: "p2p_dijkstra",
          mode_label: modeLabel,
          is_projected: isProjected,
          active_terms: costSurface.active_terms || ["ExG"],
          distance_meters: isProjected ? totalDistanceMetres.toFixed(1) : "UNAVAILABLE",
          travel_time_minutes: isProjected ? totalMinutes.toFixed(2) : "UNAVAILABLE",
          pixel_distance: totalStepsPx.toFixed(1),
          start_coords: startLatLng,
          end_coords: endLatLng,
        },
      },
    ],
  };

  return {
    geojson,
    pathCoordinates: pathCoordinates.map(([lon, lat]) => [lat, lon]),
    is_projected: isProjected,
    distance_meters: isProjected ? totalDistanceMetres.toFixed(1) : "UNAVAILABLE",
    travel_time_minutes: isProjected ? totalMinutes.toFixed(2) : "UNAVAILABLE",
    pixel_distance: totalStepsPx.toFixed(1),
    mode_label: modeLabel,
    active_terms: costSurface.active_terms || ["ExG"],
  };
}
