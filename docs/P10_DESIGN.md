# P10 native 3D vertical slice

Plan recorded before implementation, 2026-10-31. Base is P9 evidence revision
23f2949, including main P8b. P9 replay divergence is preserved, not suppressed.

The 16-word planar ABI remains a compatibility module. A separate 48-word GPU
SoA stores xyz position/velocity/force/torque/angular velocity, xyzw orientation,
mass, sphere/material data, symmetric body inertia and inverse inertia tensors,
sleep counters and stable identities. This is an internal test interface, not
the postponed public world API. No convexes, meshes, joints or terrain.

Reuse StorageDevice allocation/admission, barriers, timestamp queries, checked
submission, completion retention and resource claims. Accepted state is immutable;
prediction, hash construction, narrowphase, contact impulse updates, body gather,
integration, validation and publication are distinct GPU passes. Consumers lease
bounded immutable slots. Host edits require an idle tick boundary and no leases.

Hash xyz cells; resolve collisions by checking exact signed cell coordinates.
Search all 27 neighbors. Validate the cell-size/speed/radius envelope on every
tick so finite capacity cannot silently omit a contact. Contacts have bounded
capacity, per-body adjacency, a 3D normal and an accumulated tangent vector.
Speculative normal constraints prevent crossing within a fixed step; this is
not an exact time-of-impact integrator. Arbitrary unit-normal static planes use
the same impulse model. Friction projects onto a circular Coulomb cone, not a
single planar tangent. Tensor transforms operate through body orientation.

Parallel projected Jacobi reads prior velocities, writes per-contact impulses,
then gathers each body's impulses. Degree-based relaxation bounds coupling.
Finite iteration budgets may reject a difficult graph. Do not silently publish
an unconverged candidate. This is a coherent small/independent-contact foundation,
not a claim that large connected-island convergence is solved.

CPU independent tests reconstruct contact geometry, projected residuals,
impulse/momentum transfer, angular momentum and kinetic energy. Analytical axes,
grazing/oblique impacts, arbitrary planes, static bodies, forces/torques,
quaternions, resting/sleep/wake and failure rollback precede stress runs. Stress
reports population, actual interaction density, topology, GPU stages and CPU
verification separately. Existing planar tests retain their original thresholds.

Native ordering may vary. Accepted trajectories must satisfy numerical contracts;
bitwise equality is not a P10 prerequisite or promise. Publication rejects invalid
input, overflow, nonconvergence and violated bounds. GO requires actual headless
3D collision/rotation and independent checks, not storage or rendered appearance.
