import { useEffect, useState } from "react";
import {
  Background, BaseEdge, Controls, EdgeLabelRenderer, Handle, MarkerType,
  MiniMap, Position, ReactFlow, ReactFlowProvider, getSmoothStepPath,
  useEdgesState, useNodesState, useReactFlow,
  type Edge, type EdgeProps, type Node, type NodeProps,
} from "@xyflow/react";
import ELK from "elkjs/lib/elk.bundled.js";
import "@xyflow/react/dist/style.css";
import type { ErdLink, ErdTable } from "../utils/catalogErd";
import "./CatalogErdCanvas.css";

const elk = new ELK();
const WIDTH = 250;
const HEIGHT = 94;

interface TableData extends Record<string, unknown> {
  schema: string;
  name: string;
  comment: string | null;
  categories: string[];
  distance: number | null;
  focused: boolean;
  selected: boolean;
}

interface LinkData extends Record<string, unknown> {
  name: string | null;
  points: { x: number; y: number }[];
  showLabel: boolean;
  selected: boolean;
  incident: boolean;
  mapping: { source: string; target: string }[];
}

type FlowTable = Node<TableData, "table">;
type FlowLink = Edge<LinkData, "orthogonal">;

function TableNode({ data, selected }: NodeProps<FlowTable>) {
  const tone = data.focused ? "focused"
    : data.selected || selected ? "selected"
      : data.distance === 1 ? "hop1"
        : data.distance === 2 ? "hop2"
          : data.distance === 3 ? "hop3"
            : "normal";
  return (
    <div
      className={`dqa-erd-node dqa-erd-node-${tone}`}
      title={`${data.schema}.${data.name}`}
      data-testid={data.focused || data.selected ? "erd-highlighted-table" : undefined}
      data-erd-table={`${data.schema}.${data.name}`}
    >
      <Handle type="target" position={Position.Left} className="dqa-erd-handle" />
      <div className="dqa-erd-schema">{data.schema}</div>
      <div className="dqa-erd-table">{data.name}</div>
      <div className="dqa-erd-comment">{data.comment || "DB COMMENT 없음"}</div>
      {data.categories.length ? <div className="dqa-erd-category">{data.categories.join(", ")}</div> : null}
      {data.distance != null && data.distance > 0 ? (
        <div className="dqa-erd-hop-badge">{data.distance}단계</div>
      ) : null}
      <Handle type="source" position={Position.Right} className="dqa-erd-handle" />
    </div>
  );
}

function edgeMidpoint(points: { x: number; y: number }[]) {
  if (points.length < 2) return { x: 0, y: 0 };
  let total = 0;
  const lengths = points.slice(1).map((point, index) => {
    const last = points[index];
    const length = Math.hypot(point.x - last.x, point.y - last.y);
    total += length;
    return length;
  });
  let distance = total / 2;
  for (let i = 1; i < points.length; i += 1) {
    const length = lengths[i - 1];
    if (distance <= length && length > 0) {
      const t = distance / length;
      return { x: points[i - 1].x + (points[i].x - points[i - 1].x) * t,
        y: points[i - 1].y + (points[i].y - points[i - 1].y) * t };
    }
    distance -= length;
  }
  return points[points.length - 1];
}

function OrthogonalEdge(props: EdgeProps<FlowLink>) {
  const points = props.data?.points ?? [];
  const [fallback] = getSmoothStepPath(props);
  const path = points.length >= 2
    ? points.map((p, i) => `${i ? "L" : "M"} ${p.x} ${p.y}`).join(" ")
    : fallback;
  const middle = edgeMidpoint(points);
  const selected = Boolean(props.data?.selected);
  const incident = Boolean(props.data?.incident);
  const stroke = selected ? "#1d4ed8" : incident ? "#2563eb" : "#94a3b8";
  const width = selected ? 3.1 : incident ? 2.2 : 1.5;
  return (
    <>
      <BaseEdge path={path} markerEnd={props.markerEnd}
        style={{ stroke, strokeWidth: width }} />
      {(props.data?.showLabel || selected) && points.length >= 2 ? (
        <EdgeLabelRenderer>
          <div
            className={`dqa-erd-edge-label nodrag nopan${selected ? " selected" : ""}`}
            style={{
              transform: `translate(-50%, -50%) translate(${middle.x}px,${middle.y}px)`,
            }}
            data-testid={selected ? "erd-highlighted-link-label" : undefined}
          >
            {props.data?.name ?? "FK"}
            {selected && props.data?.mapping?.length ? (
              <span className="dqa-erd-edge-map">
                {props.data.mapping.map((item) => `${item.source}→${item.target}`).join(", ")}
              </span>
            ) : null}
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}

const nodeTypes = { table: TableNode };
const edgeTypes = { orthogonal: OrthogonalEdge };

async function layout(
  tables: ErdTable[], links: ErdLink[], distances: Map<string, number>, focus: string,
  categoryNames: Record<string, string>,
) {
  const graph = {
    id: "root",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": "RIGHT",
      "elk.edgeRouting": "ORTHOGONAL",
      "elk.spacing.nodeNode": "72",
      "elk.layered.spacing.nodeNodeBetweenLayers": "120",
      "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
      "elk.padding": "[top=45,left=45,bottom=45,right=45]",
    },
    children: tables.map((table) => ({ id: table.id, width: WIDTH, height: HEIGHT })),
    edges: links.map((link, index) => ({ id: `edge-${index}`, sources: [link.source], targets: [link.target] })),
  };
  const result = await elk.layout(graph);
  const positions = new Map((result.children ?? []).map((node) => [node.id, node]));
  const nodes: FlowTable[] = tables.map((table) => {
    const position = positions.get(table.id);
    return {
      id: table.id, type: "table",
      position: { x: position?.x ?? 0, y: position?.y ?? 0 },
      sourcePosition: Position.Right, targetPosition: Position.Left,
      style: { width: WIDTH, height: HEIGHT },
      data: { schema: table.schema, name: table.name, comment: table.comment,
        categories: table.categories.map((id) => categoryNames[id] ?? id),
        distance: distances.get(table.id) ?? null,
        focused: focus === table.id,
        selected: false },
    };
  });
  const edges: FlowLink[] = (result.edges ?? []).map((edge) => {
    const index = Number(edge.id.replace("edge-", ""));
    const original = links[index];
    const layoutEdge = edge as typeof edge & { sections?: Array<{
      startPoint: { x: number; y: number };
      endPoint: { x: number; y: number };
      bendPoints?: { x: number; y: number }[];
    }> };
    const section = layoutEdge.sections?.[0];
    const points = section
      ? [section.startPoint, ...(section.bendPoints ?? []), section.endPoint]
      : [];
    return {
      id: original.id,
      type: "orthogonal", source: original.source, target: original.target,
      markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 },
      data: { name: original.name, points,
        showLabel: links.length <= 16 && distances.size > 0,
        selected: false,
        incident: false,
        mapping: original.mapping },
    };
  });
  return { nodes, edges };
}

interface Props {
  tables: ErdTable[];
  links: ErdLink[];
  distances: Map<string, number>;
  focus: string;
  categoryNames: Record<string, string>;
  selectedTable: string;
  selectedLink: string;
  onTableSelect: (id: string) => void;
  onLinkSelect: (id: string) => void;
}

function GraphCanvas(props: Props) {
  const [nodes, setNodes, onNodesChange] = useNodesState<FlowTable>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<FlowLink>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const { fitView } = useReactFlow<FlowTable, FlowLink>();
  const { tables, links, distances, focus, categoryNames, selectedTable, selectedLink } = props;

  useEffect(() => {
    let current = true;
    setStatus("loading");
    layout(tables, links, distances, focus, categoryNames).then((result) => {
      if (!current) return;
      setNodes(result.nodes.map((node) => ({
        ...node,
        data: { ...node.data, selected: node.id === selectedTable },
        selected: node.id === selectedTable,
      })));
      setEdges(result.edges.map((edge) => ({
        ...edge,
        data: {
          ...edge.data!,
          selected: edge.id === selectedLink,
          incident: Boolean(selectedTable) &&
            (edge.source === selectedTable || edge.target === selectedTable),
        },
      })));
      setStatus("ready");
      requestAnimationFrame(() => {
        if (!current) return;
        if (selectedTable || focus) {
          void fitView({
            nodes: [{ id: selectedTable || focus }],
            padding: 0.35,
            duration: 280,
            maxZoom: 1.2,
          });
        } else {
          void fitView({ padding: 0.15, duration: 250, maxZoom: 1.15 });
        }
      });
    }).catch(() => {
      if (current) setStatus("error");
    });
    return () => { current = false; };
    // selectedTable/selectedLink are applied in a separate effect so layout is not rebuilt on every click.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tables, links, distances, focus, categoryNames, setNodes, setEdges, fitView]);

  useEffect(() => {
    if (status !== "ready") return;
    setNodes((current) => current.map((node) => ({
      ...node,
      selected: node.id === selectedTable,
      data: { ...node.data, selected: node.id === selectedTable },
    })));
    setEdges((current) => current.map((edge) => ({
      ...edge,
      data: {
        ...edge.data!,
        selected: edge.id === selectedLink,
        incident: Boolean(selectedTable) &&
          (edge.source === selectedTable || edge.target === selectedTable),
      },
    })));
    if (selectedTable) {
      requestAnimationFrame(() => {
        void fitView({
          nodes: [{ id: selectedTable }],
          padding: 0.35,
          duration: 220,
          maxZoom: 1.2,
        });
      });
    }
  }, [selectedTable, selectedLink, status, setNodes, setEdges, fitView]);

  return <div className="dqa-erd-canvas">
    {status === "loading" ? <div className="dqa-erd-status" role="status">ELK 자동 배치 계산 중…</div> : null}
    {status === "error" ? <div className="dqa-erd-status dqa-erd-error" role="alert">
      ERD 자동 배치에 실패했습니다. 범위를 좁혀 다시 시도해 주세요.
    </div> : null}
    <ReactFlow<FlowTable, FlowLink>
      nodes={nodes} edges={edges}
      nodeTypes={nodeTypes} edgeTypes={edgeTypes}
      onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
      onNodeClick={(_, node) => props.onTableSelect(node.id)}
      onEdgeClick={(_, edge) => props.onLinkSelect(edge.id)}
      onPaneClick={() => props.onLinkSelect("")}
      nodesConnectable={false} nodesDraggable={false}
      nodesFocusable edgesFocusable
      minZoom={0.08} maxZoom={2.2} fitView
      proOptions={{ hideAttribution: true }}
    >
      <MiniMap pannable zoomable nodeColor={(node) =>
        node.id === props.selectedTable ? "#16a34a" :
          distances.get(node.id) === 1 ? "#2563eb" : "#94a3b8"} />
      <Controls showInteractive={false} />
      <Background gap={18} size={1} color="#e2e8f0" />
    </ReactFlow>
  </div>;
}

export function CatalogErdCanvas(props: Props) {
  return <div className="dqa-erd-root" aria-label="Catalog ERD 그래프">
    <div className="dqa-erd-toolbar">
      <span><strong>React Flow</strong> + ELK layered / orthogonal</span>
      <span>Pan · Zoom · MiniMap</span>
      {props.distances.size === 0 ? <span>관계선 레이블은 상세 패널에서 확인</span> : null}
    </div>
    <ReactFlowProvider><GraphCanvas {...props} /></ReactFlowProvider>
  </div>;
}
