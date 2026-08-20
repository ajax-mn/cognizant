import dagre from "dagre";
import { type Node, type Edge, MarkerType, Position } from "@xyflow/react";
import type { SchemaColumn, SchemaResponse } from "../api";

export interface TableNodeData {
  tableName: string;
  columns: SchemaColumn[];
  rowCount?: number;
  [key: string]: unknown;
}

export const NODE_WIDTH = 280;
export const HEADER_HEIGHT = 44;
export const ROW_HEIGHT = 32;
export const PADDING_HEIGHT = 16;

/**
 * Calculates dynamic height of a table node based on its column count.
 */
export function getTableNodeHeight(columnCount: number): number {
  return HEADER_HEIGHT + columnCount * ROW_HEIGHT + PADDING_HEIGHT;
}

/**
 * Uses Dagre to automatically position nodes in a Left-to-Right hierarchical graph.
 */
export function getLayoutedElements<T extends Record<string, unknown> = TableNodeData>(
  nodes: Node<T>[],
  edges: Edge[],
  direction: "LR" | "TB" = "LR"
): { nodes: Node<T>[]; edges: Edge[] } {
  if (nodes.length === 0) {
    return { nodes, edges };
  }

  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));

  dagreGraph.setGraph({
    rankdir: direction,
    ranksep: 260, // Horizontal space between ranks (>= 250px)
    nodesep: 60,  // Vertical space between nodes in the same rank (>= 50px)
    align: "UL",
    ranker: "network-simplex",
  });

  nodes.forEach((node) => {
    const data = node.data as { columns?: SchemaColumn[] } | undefined;
    const colCount = Array.isArray(data?.columns) ? data.columns.length : 4;
    const height = getTableNodeHeight(colCount);

    dagreGraph.setNode(node.id, { width: NODE_WIDTH, height });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  const layoutedNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    const data = node.data as { columns?: SchemaColumn[] } | undefined;
    const colCount = Array.isArray(data?.columns) ? data.columns.length : 4;
    const height = getTableNodeHeight(colCount);

    return {
      ...node,
      targetPosition: direction === "LR" ? Position.Left : Position.Top,
      sourcePosition: direction === "LR" ? Position.Right : Position.Bottom,
      // Dagre returns center coordinates (x, y); React Flow uses top-left
      position: {
        x: (nodeWithPosition?.x ?? 0) - NODE_WIDTH / 2,
        y: (nodeWithPosition?.y ?? 0) - height / 2,
      },
    };
  });

  return { nodes: layoutedNodes, edges };
}

/**
 * Maps raw SchemaResponse into unpositioned React Flow nodes and edges,
 * then applies Dagre layout to position them Left-to-Right.
 */
export function mapSchemaToFlow(schema: SchemaResponse | null): {
  nodes: Node<TableNodeData>[];
  edges: Edge[];
} {
  if (!schema || !schema.tables) {
    return { nodes: [], edges: [] };
  }

  const tableNames = Object.keys(schema.tables);
  if (tableNames.length === 0) {
    return { nodes: [], edges: [] };
  }

  const rawRelationships = schema.relationships || [];

  // Create initial nodes
  const rawNodes: Node<TableNodeData>[] = tableNames.map((tableName) => {
    const columns = schema.tables[tableName] || [];
    return {
      id: tableName,
      type: "tableNode",
      position: { x: 0, y: 0 },
      data: {
        tableName,
        columns,
      },
    };
  });

  // Create edges: Orient from Parent Table (target_table) -> Child Table (source_table)
  // so Dagre places Parent on the left and Child on the right with smooth forward flow.
  const rawEdges: Edge[] = rawRelationships.map((rel, idx) => {
    const parentTable = rel.target_table;
    const parentCol = rel.target_column;
    const childTable = rel.source_table;
    const childCol = rel.source_column;

    const edgeId = rel.id || `edge-${parentTable}.${parentCol}->${childTable}.${childCol}-${idx}`;

    return {
      id: edgeId,
      source: parentTable,
      target: childTable,
      sourceHandle: `${parentTable}-${parentCol}-source`,
      targetHandle: `${childTable}-${childCol}-target`,
      type: "smoothstep",
      animated: true,
      style: {
        stroke: "#3b82f6",
        strokeWidth: 2,
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        width: 14,
        height: 14,
        color: "#3b82f6",
      },
      label: `${parentCol} → ${childCol}`,
      labelStyle: {
        fontSize: 10,
        fontWeight: 600,
        fill: "#475569",
      },
      labelBgStyle: {
        fill: "#ffffff",
        fillOpacity: 0.95,
        stroke: "#cbd5e1",
        strokeWidth: 1,
        rx: 4,
        ry: 4,
      },
      labelBgPadding: [6, 2],
    };
  });

  // Run through Dagre layout
  return getLayoutedElements(rawNodes, rawEdges, "LR");
}
