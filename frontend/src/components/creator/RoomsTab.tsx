/**
 * RoomsTab — Visual room graph editor using React Flow.
 *
 * Users can add rooms (nodes), connect them with doors (edges),
 * and select a room to edit its properties in a side panel (or bottom sheet on mobile).
 * Edge labels show locked/unlocked status for doors.
 * An "Auto-generate" button uses the world bible to populate rooms.
 */

import { useState, useCallback, useMemo, useRef, useEffect } from 'react'
import {
  ReactFlow,
  Controls,
  Background,
  BackgroundVariant,
  useNodesState,
  useEdgesState,
  addEdge,
  type Node,
  type Edge,
  type Connection,
  type NodeTypes,
  type EdgeTypes,
  Handle,
  Position,
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type NodeProps,
  type EdgeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import {
  Plus, X, DoorOpen, Lock, Unlock, Sparkles, Loader2,
  Trash2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { RoomNode, SceneCreatorState } from '@/pages/Creator'

/* ------------------------------------------------------------------ */
/*  Custom Room Node                                                   */
/* ------------------------------------------------------------------ */

type RoomNodeData = {
  label: string
  description: string
  entities: string[]
  selected?: boolean
}

function RoomNodeComponent({ data, selected }: NodeProps<Node<RoomNodeData>>) {
  return (
    <div
      className={cn(
        'px-4 py-3 rounded-xl border-2 min-w-[140px] max-w-[200px] transition-colors',
        'bg-bg-secondary shadow-lg shadow-black/30',
        selected
          ? 'border-gold ring-2 ring-gold/30'
          : 'border-border hover:border-text-muted',
      )}
    >
      {/* Handles for connecting edges */}
      <Handle
        type="target"
        position={Position.Top}
        className="!w-3 !h-3 !bg-gold/60 !border-gold/30 !border-2"
      />
      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-3 !h-3 !bg-gold/60 !border-gold/30 !border-2"
      />
      <Handle
        type="target"
        position={Position.Left}
        id="left"
        className="!w-3 !h-3 !bg-gold/60 !border-gold/30 !border-2"
      />
      <Handle
        type="source"
        position={Position.Right}
        id="right"
        className="!w-3 !h-3 !bg-gold/60 !border-gold/30 !border-2"
      />

      <div className="flex items-center gap-2 mb-1">
        <DoorOpen className="size-4 text-gold shrink-0" />
        <span className="text-text-primary text-sm font-semibold truncate">
          {data.label}
        </span>
      </div>
      {data.description && (
        <p className="text-text-muted text-[11px] leading-snug line-clamp-2">
          {data.description}
        </p>
      )}
      {data.entities && data.entities.length > 0 && (
        <div className="flex items-center gap-1 mt-1.5">
          <span className="text-[10px] text-text-muted/60">
            {data.entities.length} {data.entities.length === 1 ? 'entity' : 'entities'}
          </span>
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Custom Door Edge                                                   */
/* ------------------------------------------------------------------ */

type DoorEdgeData = {
  locked: boolean
  label: string
}

function DoorEdgeComponent({
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style = {},
  data,
}: EdgeProps<Edge<DoorEdgeData>>) {
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
          className="flex items-center gap-1 px-2 py-1 rounded-md bg-bg-secondary border border-border text-[10px] shadow-md"
        >
          {locked ? (
            <Lock className="size-3 text-danger" />
          ) : (
            <Unlock className="size-3 text-success" />
          )}
          <span className={locked ? 'text-danger' : 'text-success'}>
            {data?.label || (locked ? 'Locked' : 'Open')}
          </span>
        </div>
      </EdgeLabelRenderer>
    </>
  )
}

/* ------------------------------------------------------------------ */
/*  Room detail panel (side panel on desktop, bottom sheet on mobile)   */
/* ------------------------------------------------------------------ */

function RoomDetailPanel({
  room,
  onUpdate,
  onDelete,
  onClose,
}: {
  room: RoomNode
  onUpdate: (room: RoomNode) => void
  onDelete: (id: string) => void
  onClose: () => void
}) {
  const [name, setName] = useState(room.name)
  const [description, setDescription] = useState(room.description)
  const [entityInput, setEntityInput] = useState('')
  const [entities, setEntities] = useState<string[]>(room.entities)

  // Swipe-to-dismiss for mobile bottom sheet
  const touchStartY = useRef<number | null>(null)
  const [dragY, setDragY] = useState(0)
  const [isDragging, setIsDragging] = useState(false)

  // Sync when selection changes
  useEffect(() => {
    setName(room.name)
    setDescription(room.description)
    setEntities(room.entities)
  }, [room.id, room.name, room.description, room.entities])

  // Push changes to parent
  useEffect(() => {
    const timer = setTimeout(() => {
      onUpdate({ ...room, name, description, entities })
    }, 300)
    return () => clearTimeout(timer)
  }, [name, description, entities])

  const addEntity = () => {
    const trimmed = entityInput.trim()
    if (trimmed && !entities.includes(trimmed)) {
      setEntities(prev => [...prev, trimmed])
      setEntityInput('')
    }
  }

  const removeEntity = (entity: string) => {
    setEntities(prev => prev.filter(e => e !== entity))
  }

  const handleTouchStart = (e: React.TouchEvent) => {
    touchStartY.current = e.touches[0].clientY
  }

  const handleTouchMove = (e: React.TouchEvent) => {
    if (touchStartY.current === null) return
    const dy = e.touches[0].clientY - touchStartY.current
    if (dy > 0) {
      setDragY(dy)
      setIsDragging(true)
    }
  }

  const handleTouchEnd = () => {
    if (dragY > 100) {
      onClose()
    }
    setDragY(0)
    setIsDragging(false)
    touchStartY.current = null
  }

  return (
    <>
      {/* Mobile: bottom sheet overlay */}
      <div className="md:hidden fixed inset-0 z-50">
        {/* Backdrop */}
        <div className="absolute inset-0 bg-black/50" onClick={onClose} />

        {/* Sheet */}
        <div
          className="absolute bottom-0 left-0 right-0 bg-bg-secondary rounded-t-2xl border-t border-x border-border max-h-[70vh] overflow-y-auto"
          style={{
            transform: `translateY(${dragY}px)`,
            transition: isDragging ? 'none' : 'transform 200ms ease-out',
          }}
          onTouchStart={handleTouchStart}
          onTouchMove={handleTouchMove}
          onTouchEnd={handleTouchEnd}
        >
          {/* Drag handle */}
          <div className="flex justify-center pt-3 pb-1 sticky top-0 bg-bg-secondary">
            <div className="w-10 h-1 rounded-full bg-text-muted" />
          </div>

          <div className="px-4 pb-6 space-y-4">
            <RoomForm
              name={name}
              setName={setName}
              description={description}
              setDescription={setDescription}
              entities={entities}
              entityInput={entityInput}
              setEntityInput={setEntityInput}
              addEntity={addEntity}
              removeEntity={removeEntity}
              onDelete={() => onDelete(room.id)}
            />
          </div>
        </div>
      </div>

      {/* Desktop: side panel */}
      <div className="hidden md:block w-80 border-l border-border bg-bg-secondary overflow-y-auto">
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h3 className="text-text-primary font-semibold text-sm">Edit Room</h3>
          <button
            onClick={onClose}
            className="size-9 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-tertiary transition-colors"
          >
            <X className="size-4" />
          </button>
        </div>
        <div className="px-4 py-4 space-y-4">
          <RoomForm
            name={name}
            setName={setName}
            description={description}
            setDescription={setDescription}
            entities={entities}
            entityInput={entityInput}
            setEntityInput={setEntityInput}
            addEntity={addEntity}
            removeEntity={removeEntity}
            onDelete={() => onDelete(room.id)}
          />
        </div>
      </div>
    </>
  )
}

/* ------------------------------------------------------------------ */
/*  Shared room form fields                                            */
/* ------------------------------------------------------------------ */

function RoomForm({
  name,
  setName,
  description,
  setDescription,
  entities,
  entityInput,
  setEntityInput,
  addEntity,
  removeEntity,
  onDelete,
}: {
  name: string
  setName: (v: string) => void
  description: string
  setDescription: (v: string) => void
  entities: string[]
  entityInput: string
  setEntityInput: (v: string) => void
  addEntity: () => void
  removeEntity: (e: string) => void
  onDelete: () => void
}) {
  return (
    <>
      <div>
        <label className="block text-text-secondary text-xs font-medium mb-1">Room Name</label>
        <input
          type="text"
          value={name}
          onChange={e => setName(e.target.value)}
          className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-gold/30 focus:border-gold/50"
        />
      </div>

      <div>
        <label className="block text-text-secondary text-xs font-medium mb-1">Description</label>
        <textarea
          value={description}
          onChange={e => setDescription(e.target.value)}
          rows={3}
          className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-gold/30 focus:border-gold/50 resize-y"
        />
      </div>

      <div>
        <label className="block text-text-secondary text-xs font-medium mb-1">Entities</label>
        <div className="flex gap-2 mb-2">
          <input
            type="text"
            value={entityInput}
            onChange={e => setEntityInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addEntity() } }}
            placeholder="Add entity..."
            className="flex-1 rounded-lg border border-border bg-bg-primary px-3 py-2 text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-gold/30 focus:border-gold/50"
          />
          <Button onClick={addEntity} variant="outline" className="h-10 px-3">
            <Plus className="size-4" />
          </Button>
        </div>
        {entities.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {entities.map(entity => (
              <span
                key={entity}
                className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-bg-tertiary text-text-secondary text-xs"
              >
                {entity}
                <button
                  onClick={() => removeEntity(entity)}
                  className="size-4 min-h-0 min-w-0 flex items-center justify-center rounded text-text-muted hover:text-danger transition-colors"
                >
                  <X className="size-3" />
                </button>
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="pt-2 border-t border-border">
        <Button
          variant="destructive"
          onClick={onDelete}
          className="w-full h-10 gap-2 text-sm"
        >
          <Trash2 className="size-4" />
          Delete Room
        </Button>
      </div>
    </>
  )
}

/* ------------------------------------------------------------------ */
/*  Main RoomsTab Component                                            */
/* ------------------------------------------------------------------ */

const nodeTypes: NodeTypes = { room: RoomNodeComponent }
const edgeTypes: EdgeTypes = { door: DoorEdgeComponent }

let nodeIdCounter = 0
function nextNodeId() {
  return `room-${++nodeIdCounter}-${Date.now()}`
}

export function RoomsTab({
  sceneState,
  setSceneState,
}: {
  sceneState: SceneCreatorState
  setSceneState: React.Dispatch<React.SetStateAction<SceneCreatorState>>
}) {
  // Convert scene rooms to React Flow nodes
  const initialNodes: Node<RoomNodeData>[] = useMemo(
    () =>
      sceneState.rooms.map(r => ({
        id: r.id,
        type: 'room',
        position: { x: r.x, y: r.y },
        data: {
          label: r.name,
          description: r.description,
          entities: r.entities,
        },
      })),
    [], // only run on mount — we manage nodes ourselves after that
  )

  const initialEdges: Edge<DoorEdgeData>[] = useMemo(
    () =>
      (sceneState.doors ?? []).map(d => ({
        id: d.id,
        source: d.sourceRoomId,
        target: d.targetRoomId,
        type: 'door',
        data: { locked: d.locked, label: d.label },
      })),
    [],
  )

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)
  const [selectedRoomId, setSelectedRoomId] = useState<string | null>(null)
  const [autoGenerating, setAutoGenerating] = useState(false)

  // Find the selected room from scene state
  const selectedRoom = useMemo(() => {
    if (!selectedRoomId) return null
    const node = nodes.find(n => n.id === selectedRoomId)
    if (!node) return null
    return {
      id: node.id,
      name: node.data.label,
      description: node.data.description,
      entities: node.data.entities,
      x: node.position.x,
      y: node.position.y,
    } as RoomNode
  }, [selectedRoomId, nodes])

  // Sync nodes/edges back to sceneState
  const syncToSceneState = useCallback(() => {
    setSceneState(prev => ({
      ...prev,
      rooms: nodes.map(n => ({
        id: n.id,
        name: n.data.label,
        description: n.data.description,
        entities: n.data.entities,
        x: n.position.x,
        y: n.position.y,
      })),
      doors: edges.map(e => ({
        id: e.id,
        sourceRoomId: e.source,
        targetRoomId: e.target,
        locked: (e.data as DoorEdgeData)?.locked ?? false,
        label: (e.data as DoorEdgeData)?.label ?? 'Door',
      })),
    }))
  }, [nodes, edges, setSceneState])

  // Debounced sync
  useEffect(() => {
    const timer = setTimeout(syncToSceneState, 500)
    return () => clearTimeout(timer)
  }, [syncToSceneState])

  // Handle new edge connection
  const onConnect = useCallback(
    (connection: Connection) => {
      const newEdge: Edge<DoorEdgeData> = {
        ...connection,
        id: `door-${connection.source}-${connection.target}`,
        type: 'door',
        data: { locked: false, label: 'Door' },
      }
      setEdges(eds => addEdge(newEdge, eds))
    },
    [setEdges],
  )

  // Handle node click for selection
  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedRoomId(node.id)
  }, [])

  // Handle pane click to deselect
  const onPaneClick = useCallback(() => {
    setSelectedRoomId(null)
  }, [])

  // Add a new room
  const addRoom = useCallback(() => {
    const id = nextNodeId()
    const roomNumber = nodes.length + 1
    const newNode: Node<RoomNodeData> = {
      id,
      type: 'room',
      position: {
        x: 100 + (nodes.length % 3) * 250,
        y: 100 + Math.floor(nodes.length / 3) * 200,
      },
      data: {
        label: `Room ${roomNumber}`,
        description: '',
        entities: [],
      },
    }
    setNodes(nds => [...nds, newNode])
    setSelectedRoomId(id)
  }, [nodes.length, setNodes])

  // Update a room from the detail panel
  const updateRoom = useCallback(
    (room: RoomNode) => {
      setNodes(nds =>
        nds.map(n =>
          n.id === room.id
            ? {
                ...n,
                data: {
                  label: room.name,
                  description: room.description,
                  entities: room.entities,
                },
              }
            : n,
        ),
      )
    },
    [setNodes],
  )

  // Delete a room
  const deleteRoom = useCallback(
    (id: string) => {
      setNodes(nds => nds.filter(n => n.id !== id))
      setEdges(eds => eds.filter(e => e.source !== id && e.target !== id))
      if (selectedRoomId === id) setSelectedRoomId(null)
    },
    [selectedRoomId, setNodes, setEdges],
  )

  // Toggle edge locked status on click
  const onEdgeClick = useCallback(
    (_: React.MouseEvent, edge: Edge) => {
      setEdges(eds =>
        eds.map(e =>
          e.id === edge.id
            ? {
                ...e,
                data: {
                  ...((e.data as DoorEdgeData) ?? { locked: false, label: 'Door' }),
                  locked: !((e.data as DoorEdgeData)?.locked ?? false),
                  label: (e.data as DoorEdgeData)?.locked ? 'Open' : 'Locked',
                },
              }
            : e,
        ),
      )
    },
    [setEdges],
  )

  // Auto-generate rooms from world bible
  const autoGenerate = useCallback(async () => {
    if (!sceneState.worldBible) return
    setAutoGenerating(true)

    try {
      // Use the themes API to get room data for current theme
      const res = await fetch('/api/themes')
      if (!res.ok) throw new Error('Failed to fetch themes')
      const data = await res.json()
      const themeData = data.themes?.[sceneState.theme]

      if (!themeData?.rooms) {
        throw new Error('No rooms found for theme')
      }

      // Generate nodes from theme rooms
      const numRooms = Math.min(3 + sceneState.difficulty, themeData.rooms.length)
      const roomSlice = themeData.rooms.slice(0, numRooms)

      const newNodes: Node<RoomNodeData>[] = roomSlice.map(
        (room: { name: string; desc: string }, i: number) => ({
          id: nextNodeId(),
          type: 'room',
          position: {
            x: 150 + (i % 3) * 280,
            y: 100 + Math.floor(i / 3) * 220,
          },
          data: {
            label: room.name,
            description: room.desc,
            entities: [],
          },
        }),
      )

      // Auto-connect rooms in a chain
      const newEdges: Edge<DoorEdgeData>[] = []
      for (let i = 0; i < newNodes.length - 1; i++) {
        newEdges.push({
          id: `door-${newNodes[i].id}-${newNodes[i + 1].id}`,
          source: newNodes[i].id,
          target: newNodes[i + 1].id,
          type: 'door',
          data: {
            locked: i > 0, // first door is open, rest are locked
            label: i > 0 ? 'Locked' : 'Open',
          },
        })
      }

      setNodes(newNodes)
      setEdges(newEdges)
    } catch (err) {
      console.error('Auto-generate failed:', err)
    } finally {
      setAutoGenerating(false)
    }
  }, [sceneState.worldBible, sceneState.theme, sceneState.difficulty, setNodes, setEdges])

  return (
    <div className="flex flex-col h-full -mx-4 -mt-4 md:-mx-6">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-border bg-bg-secondary md:px-6">
        <Button onClick={addRoom} variant="outline" className="h-10 gap-2 text-sm">
          <Plus className="size-4" />
          Add Room
        </Button>

        {sceneState.worldBible && (
          <Button
            onClick={autoGenerate}
            disabled={autoGenerating}
            className="h-10 gap-2 text-sm bg-gold hover:bg-gold-bright text-bg-primary"
          >
            {autoGenerating ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Sparkles className="size-4" />
            )}
            Auto-generate
          </Button>
        )}

        <span className="ml-auto text-text-muted text-xs">
          {nodes.length} {nodes.length === 1 ? 'room' : 'rooms'} | {edges.length} {edges.length === 1 ? 'door' : 'doors'}
        </span>
      </div>

      {/* Graph canvas + optional side panel */}
      <div className="flex flex-1 min-h-[400px] md:min-h-[500px]" style={{ height: 'calc(100vh - 280px)' }}>
        <div className="flex-1 relative">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            onEdgeClick={onEdgeClick}
            onPaneClick={onPaneClick}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            fitView
            minZoom={0.3}
            maxZoom={2}
            className="bg-bg-primary"
            proOptions={{ hideAttribution: true }}
            /* Touch/gesture support is built-in with React Flow:
               - pinch-to-zoom
               - two-finger pan
               - tap nodes to select
            */
          >
            <Controls
              position="bottom-left"
              className="!bg-bg-secondary !border-border !rounded-lg !shadow-lg [&>button]:!bg-bg-secondary [&>button]:!border-border [&>button]:!text-text-secondary [&>button:hover]:!bg-bg-tertiary [&>button]:!min-h-[44px] [&>button]:!min-w-[44px] [&>button]:!w-11 [&>button]:!h-11 [&>button>svg]:!fill-text-secondary"
            />
            <Background
              variant={BackgroundVariant.Dots}
              gap={20}
              size={1}
              color="#30363d"
            />
          </ReactFlow>

          {/* Empty state overlay */}
          {nodes.length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="text-center px-6">
                <DoorOpen className="size-10 text-text-muted/30 mx-auto mb-3" />
                <p className="text-text-muted text-sm mb-2">No rooms yet</p>
                <p className="text-text-muted/60 text-xs">
                  Click "Add Room" or "Auto-generate" to get started
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Desktop side panel for room editing */}
        {selectedRoom && (
          <RoomDetailPanel
            room={selectedRoom}
            onUpdate={updateRoom}
            onDelete={deleteRoom}
            onClose={() => setSelectedRoomId(null)}
          />
        )}
      </div>
    </div>
  )
}
