/**
 * InteractiveMap — read-only room graph for the Game Monitor.
 *
 * Renders the current room topology using React Flow in view-only mode.
 * Shows agent positions as animated markers on their current room.
 * Edges colored by door status (locked=red, unlocked=green).
 * Click a room to see entity list and current occupants.
 * Optional heat map toggle (room visit frequency).
 *
 * Mobile: full-screen overlay triggered by a map FAB, pinch-to-zoom.
 * Desktop: inline collapsible panel.
 */

import { useState, useCallback, useMemo, useRef, useEffect } from 'react'
import {
  ReactFlow,
  Controls,
  Background,
  BackgroundVariant,
  type Node,
  type Edge,
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  Handle,
  Position,
  type NodeProps,
  type EdgeProps,
  type NodeTypes,
  type EdgeTypes,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import {
  Map,
  X,
  Lock,
  Unlock,
  User,
  Flame,
  Package,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  useRooms,
  useAgents,
  useDoors,
  useNarrativeEvents,
} from '@/stores/gameStore'
import type { AgentState, Room, Door, Entity } from '@/types/game'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type MapRoomNodeData = {
  label: string
  description: string
  agents: AgentState[]
  entityCount: number
  heatValue: number // 0-1, how often this room is visited
  showHeat: boolean
}

type MapDoorEdgeData = {
  locked: boolean
  label: string
}

// ---------------------------------------------------------------------------
// Custom Room Node — shows name + agent markers
// ---------------------------------------------------------------------------

function MapRoomNode({ data, selected }: NodeProps<Node<MapRoomNodeData>>) {
  // Heat map coloring: interpolate from default bg to warm orange
  const heatBg = data.showHeat && data.heatValue > 0
    ? `rgba(227, 179, 65, ${0.05 + data.heatValue * 0.3})`
    : undefined

  return (
    <div
      className={cn(
        'px-3 py-2.5 rounded-xl border-2 min-w-[120px] max-w-[180px] transition-colors cursor-pointer',
        'bg-bg-secondary shadow-lg shadow-black/30',
        selected
          ? 'border-gold ring-2 ring-gold/30'
          : 'border-border hover:border-text-muted',
      )}
      style={heatBg ? { backgroundColor: heatBg } : undefined}
    >
      {/* Connection handles (hidden but functional for layout) */}
      <Handle type="target" position={Position.Top} className="!w-0 !h-0 !bg-transparent !border-0 !min-w-0 !min-h-0" />
      <Handle type="source" position={Position.Bottom} className="!w-0 !h-0 !bg-transparent !border-0 !min-w-0 !min-h-0" />
      <Handle type="target" position={Position.Left} id="left" className="!w-0 !h-0 !bg-transparent !border-0 !min-w-0 !min-h-0" />
      <Handle type="source" position={Position.Right} id="right" className="!w-0 !h-0 !bg-transparent !border-0 !min-w-0 !min-h-0" />

      {/* Room name */}
      <div className="text-sm font-semibold text-text-primary truncate mb-1">
        {data.label}
      </div>

      {/* Entity count */}
      {data.entityCount > 0 && (
        <div className="text-[10px] text-text-muted mb-1.5">
          {data.entityCount} {data.entityCount === 1 ? 'entity' : 'entities'}
        </div>
      )}

      {/* Agent markers — colored dots with names */}
      {data.agents.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {data.agents.map((agent) => (
            <span
              key={agent.id}
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-gold/15 text-gold text-[10px] font-medium"
              title={agent.name}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-gold animate-pulse" />
              {agent.name.length > 8 ? agent.name.slice(0, 7) + '...' : agent.name}
            </span>
          ))}
        </div>
      )}

      {/* Heat indicator */}
      {data.showHeat && data.heatValue > 0 && (
        <div className="mt-1 flex items-center gap-1">
          <Flame size={10} className="text-warning" />
          <span className="text-[9px] text-warning">
            {Math.round(data.heatValue * 100)}%
          </span>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Custom Door Edge — colored by lock status
// ---------------------------------------------------------------------------

function MapDoorEdge({
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style = {},
  data,
}: EdgeProps<Edge<MapDoorEdgeData>>) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  })

  const locked = data?.locked ?? false

  return (
    <>
      <BaseEdge
        path={edgePath}
        style={{
          ...style,
          stroke: locked ? '#f85149' : '#3fb950',
          strokeWidth: 2,
          strokeDasharray: locked ? '6 3' : undefined,
        }}
      />
      <EdgeLabelRenderer>
        <div
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            pointerEvents: 'all',
          }}
          className="flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-bg-secondary border border-border text-[9px] shadow-md"
        >
          {locked ? (
            <Lock className="size-2.5 text-danger" />
          ) : (
            <Unlock className="size-2.5 text-success" />
          )}
          <span className={locked ? 'text-danger' : 'text-success'}>
            {data?.label || (locked ? 'Locked' : 'Open')}
          </span>
        </div>
      </EdgeLabelRenderer>
    </>
  )
}

// ---------------------------------------------------------------------------
// Room detail popup — entity list + occupants
// ---------------------------------------------------------------------------

function RoomDetailPopup({
  room,
  agents,
  onClose,
}: {
  room: Room
  agents: AgentState[]
  onClose: () => void
}) {
  const entities = Object.values(room.entities)

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-[60] bg-black/40" onClick={onClose} />

      {/* Popup — bottom sheet on mobile, centered dialog on desktop */}
      <div
        className={cn(
          'fixed z-[61] bg-bg-secondary border border-border',
          // Mobile: bottom sheet
          'inset-x-0 bottom-0 rounded-t-2xl max-h-[60vh] overflow-y-auto',
          // Desktop: centered
          'md:inset-auto md:top-1/2 md:left-1/2 md:-translate-x-1/2 md:-translate-y-1/2',
          'md:w-[380px] md:max-h-[50vh] md:rounded-xl',
        )}
      >
        {/* Drag handle (mobile) */}
        <div className="flex justify-center pt-3 pb-1 md:hidden">
          <div className="w-10 h-1 rounded-full bg-text-muted" />
        </div>

        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h3 className="text-base font-bold text-text-primary m-0">
            {room.name}
          </h3>
          <button
            onClick={onClose}
            className="w-9 h-9 min-w-[44px] min-h-[44px] flex items-center justify-center rounded-full hover:bg-bg-tertiary text-text-secondary"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        {/* Description */}
        {room.description && (
          <p className="px-4 pt-3 text-sm text-text-secondary leading-relaxed m-0">
            {room.description}
          </p>
        )}

        {/* Occupants */}
        <div className="px-4 pt-3">
          <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2 flex items-center gap-1">
            <User size={12} />
            Occupants ({agents.length})
          </h4>
          {agents.length === 0 ? (
            <p className="text-sm text-text-muted italic m-0">Empty room</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {agents.map((a) => (
                <span
                  key={a.id}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-gold/10 border border-gold/20 text-sm text-gold font-medium"
                >
                  <User size={14} />
                  {a.name}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Entities */}
        <div className="px-4 pt-3 pb-4">
          <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2 flex items-center gap-1">
            <Package size={12} />
            Entities ({entities.length})
          </h4>
          {entities.length === 0 ? (
            <p className="text-sm text-text-muted italic m-0">Nothing here</p>
          ) : (
            <div className="space-y-1.5">
              {entities.map((entity: Entity) => (
                <div
                  key={entity.id}
                  className="flex items-center justify-between px-2.5 py-2 rounded-lg bg-bg-tertiary border border-border"
                >
                  <div className="min-w-0">
                    <span className="text-sm text-text-primary font-medium block truncate">
                      {entity.name}
                    </span>
                    {entity.description && (
                      <span className="text-[11px] text-text-muted line-clamp-1">
                        {entity.description}
                      </span>
                    )}
                  </div>
                  <span className={cn(
                    'text-[10px] font-medium px-1.5 py-0.5 rounded shrink-0 ml-2',
                    entity.state === 'locked' ? 'bg-danger/15 text-danger' :
                    entity.state === 'hidden' ? 'bg-bg-secondary text-text-muted' :
                    entity.state === 'solved' ? 'bg-success/15 text-success' :
                    'bg-bg-secondary text-text-secondary',
                  )}>
                    {entity.state}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  )
}

// ---------------------------------------------------------------------------
// Node/Edge type registrations
// ---------------------------------------------------------------------------

const nodeTypes: NodeTypes = { mapRoom: MapRoomNode }
const edgeTypes: EdgeTypes = { mapDoor: MapDoorEdge }

// ---------------------------------------------------------------------------
// Layout helper — auto-position rooms in a grid
// ---------------------------------------------------------------------------

function autoLayout(roomIds: string[]): Record<string, { x: number; y: number }> {
  const positions: Record<string, { x: number; y: number }> = {}
  const cols = Math.max(2, Math.ceil(Math.sqrt(roomIds.length)))
  roomIds.forEach((id, i) => {
    const col = i % cols
    const row = Math.floor(i / cols)
    positions[id] = { x: 80 + col * 250, y: 80 + row * 200 }
  })
  return positions
}

// ---------------------------------------------------------------------------
// Main InteractiveMap component
// ---------------------------------------------------------------------------

export function InteractiveMap() {
  const rooms = useRooms()
  const agentsRecord = useAgents()
  const doorsRecord = useDoors()
  const narrativeEvents = useNarrativeEvents()
  const agents = useMemo(() => Object.values(agentsRecord), [agentsRecord])
  const roomList = useMemo(() => Object.values(rooms), [rooms])
  const doorList = useMemo(() => Object.values(doorsRecord), [doorsRecord])

  const [isOpen, setIsOpen] = useState(false) // mobile overlay state
  const [isCollapsed, setIsCollapsed] = useState(true) // desktop collapse state
  const [showHeat, setShowHeat] = useState(false)
  const [selectedRoomId, setSelectedRoomId] = useState<string | null>(null)

  // Stable position layout — compute once when rooms change
  const positionsRef = useRef<Record<string, { x: number; y: number }>>({})
  const prevRoomIdsRef = useRef<string>('')

  const roomIds = useMemo(() => Object.keys(rooms).sort(), [rooms])
  const roomIdsKey = roomIds.join(',')

  if (roomIdsKey !== prevRoomIdsRef.current) {
    positionsRef.current = autoLayout(roomIds)
    prevRoomIdsRef.current = roomIdsKey
  }

  // Compute room visit frequency from narrative events for heat map
  const roomHeat = useMemo(() => {
    const counts: Record<string, number> = {}
    let maxCount = 1
    for (const entry of narrativeEvents) {
      for (const evt of entry.events) {
        if (evt.room) {
          counts[evt.room] = (counts[evt.room] || 0) + 1
          if (counts[evt.room] > maxCount) maxCount = counts[evt.room]
        }
      }
    }
    // Normalize to 0-1
    const heat: Record<string, number> = {}
    for (const [roomId, count] of Object.entries(counts)) {
      heat[roomId] = count / maxCount
    }
    return heat
  }, [narrativeEvents])

  // Build agents-by-room lookup
  const agentsByRoom = useMemo(() => {
    const map: Record<string, AgentState[]> = {}
    for (const agent of agents) {
      if (!map[agent.room_id]) map[agent.room_id] = []
      map[agent.room_id].push(agent)
    }
    return map
  }, [agents])

  // Build React Flow nodes
  const nodes: Node<MapRoomNodeData>[] = useMemo(
    () =>
      roomList.map((room) => ({
        id: room.id,
        type: 'mapRoom',
        position: positionsRef.current[room.id] || { x: 0, y: 0 },
        data: {
          label: room.name,
          description: room.description,
          agents: agentsByRoom[room.id] || [],
          entityCount: Object.keys(room.entities).length,
          heatValue: roomHeat[room.id] || 0,
          showHeat,
        },
        selectable: true,
        draggable: false,
      })),
    [roomList, agentsByRoom, roomHeat, showHeat],
  )

  // Build React Flow edges from doors
  const edges: Edge<MapDoorEdgeData>[] = useMemo(
    () =>
      doorList.map((door: Door) => ({
        id: door.id,
        source: door.room_a,
        target: door.room_b,
        type: 'mapDoor',
        data: {
          locked: door.locked,
          label: door.name || (door.locked ? 'Locked' : 'Open'),
        },
      })),
    [doorList],
  )

  // Click room to show detail
  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedRoomId(node.id)
  }, [])

  const onPaneClick = useCallback(() => {
    setSelectedRoomId(null)
  }, [])

  // Selected room data
  const selectedRoom = selectedRoomId ? rooms[selectedRoomId] : null
  const selectedRoomAgents = selectedRoomId ? (agentsByRoom[selectedRoomId] || []) : []

  // No rooms = nothing to show
  if (roomList.length === 0) {
    return null
  }

  // The map content (shared between mobile overlay and desktop panel)
  const mapContent = (
    <div className="w-full h-full relative">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        minZoom={0.2}
        maxZoom={3}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={true}
        panOnDrag
        zoomOnPinch
        zoomOnScroll
        className="bg-bg-primary"
        proOptions={{ hideAttribution: true }}
      >
        <Controls
          position="bottom-left"
          showInteractive={false}
          className="!bg-bg-secondary !border-border !rounded-lg !shadow-lg [&>button]:!bg-bg-secondary [&>button]:!border-border [&>button]:!text-text-secondary [&>button:hover]:!bg-bg-tertiary [&>button]:!min-h-[44px] [&>button]:!min-w-[44px] [&>button]:!w-11 [&>button]:!h-11 [&>button>svg]:!fill-text-secondary"
        />
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1}
          color="#30363d"
        />
      </ReactFlow>

      {/* Heat map toggle */}
      <button
        onClick={() => setShowHeat((h) => !h)}
        className={cn(
          'absolute top-3 right-3 z-10',
          'flex items-center gap-1.5 px-3 py-2 rounded-lg',
          'text-xs font-medium min-h-[44px]',
          'border transition-colors',
          showHeat
            ? 'bg-warning/15 border-warning/30 text-warning'
            : 'bg-bg-secondary border-border text-text-secondary hover:text-text-primary',
        )}
        aria-label={showHeat ? 'Hide heat map' : 'Show heat map'}
      >
        <Flame size={14} />
        <span className="hidden sm:inline">Heat</span>
      </button>

      {/* Room detail popup */}
      {selectedRoom && (
        <RoomDetailPopup
          room={selectedRoom}
          agents={selectedRoomAgents}
          onClose={() => setSelectedRoomId(null)}
        />
      )}
    </div>
  )

  return (
    <>
      {/* ---- Mobile FAB button (bottom-right, above sim controls) ---- */}
      <button
        onClick={() => setIsOpen(true)}
        className={cn(
          'md:hidden fixed z-30 right-4 bottom-[140px]',
          'w-14 h-14 rounded-full',
          'bg-gold text-bg-primary shadow-lg shadow-gold/25',
          'flex items-center justify-center',
          'active:scale-90 transition-transform',
        )}
        aria-label="Open room map"
      >
        <Map size={24} />
      </button>

      {/* ---- Mobile full-screen overlay ---- */}
      {isOpen && (
        <div className="md:hidden fixed inset-0 z-50 bg-bg-primary flex flex-col">
          {/* Header */}
          <div className="shrink-0 flex items-center justify-between px-4 py-3 border-b border-border bg-bg-secondary">
            <h2 className="text-gold font-bold text-base m-0 flex items-center gap-2">
              <Map size={18} />
              Room Map
            </h2>
            <button
              onClick={() => setIsOpen(false)}
              className="w-11 h-11 min-w-[44px] min-h-[44px] flex items-center justify-center rounded-lg hover:bg-bg-tertiary text-text-secondary"
              aria-label="Close map"
            >
              <X size={20} />
            </button>
          </div>

          {/* Map fills remaining space */}
          <div className="flex-1 min-h-0">
            {mapContent}
          </div>
        </div>
      )}

      {/* ---- Desktop collapsible panel ---- */}
      <div className="hidden md:block shrink-0 border-b border-border bg-bg-primary">
        {/* Toggle bar */}
        <button
          onClick={() => setIsCollapsed((c) => !c)}
          className={cn(
            'w-full flex items-center justify-between px-4 py-2.5',
            'text-sm font-semibold text-text-secondary hover:text-text-primary',
            'transition-colors min-h-[44px]',
          )}
          aria-expanded={!isCollapsed}
        >
          <span className="flex items-center gap-2">
            <Map size={16} className="text-gold" />
            Room Map
            <span className="text-text-muted text-xs font-normal">
              {roomList.length} rooms, {agents.length} agents
            </span>
          </span>
          {isCollapsed ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
        </button>

        {/* Map panel */}
        {!isCollapsed && (
          <div className="h-[350px] lg:h-[420px] border-t border-border">
            {mapContent}
          </div>
        )}
      </div>
    </>
  )
}
