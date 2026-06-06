---
name: create-a-cube-actor-in-unreal-via-unreal-mcp
description: Spawn a named Static Mesh Actor with the Cube mesh in the current Unreal level using execute_python_code
version: 2.0.0
category: general
tags: [unreal, mcp, spawn, actor, python, automation]
status: active
confidence: 0.97
source: corrected
owner: "deadlyjrmint@gmail.com"
created: "2026-06-05T05:48:19Z"
updated: "2026-06-06"
---

## When to Use

User wants to spawn a cube (or any Static Mesh Actor) in the current Unreal level with a specific name and optional location.

## Procedure

1. Call `execute_python_code` with the following Python — replace `ACTOR_NAME` and the Vector coordinates with the desired values:

```python
import unreal
actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
    unreal.StaticMeshActor,
    unreal.Vector(0, 0, 0),
    unreal.Rotator(0, 0, 0)
)
actor.set_actor_label('ACTOR_NAME')
mesh = unreal.load_asset('/Engine/BasicShapes/Cube')
actor.static_mesh_component.set_static_mesh(mesh)
print(f"Spawned {actor.get_actor_label()} at {actor.get_actor_location()}")
```

2. Confirm the print output shows the correct actor name and location.

## Pitfalls

- Do NOT use `spawn_actor` MCP tool with a mesh parameter — mesh param is unreliable and was the cause of T3 R1 test failures.
- Do NOT use CLI flag syntax (`unreal_mcp spawn_actor --type ... --mesh ...`) — this format does not exist.
- For non-cube meshes change the asset path: `/Engine/BasicShapes/Sphere`, `/Engine/BasicShapes/Cylinder`, or a project asset path.

## Verification

- The print output confirms the actor name and location.
- Optionally call `execute_python_code` with `unreal.EditorLevelLibrary.get_all_level_actors()` to confirm the actor appears in the level.
