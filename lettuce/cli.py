# -*- coding: utf-8 -*-

"""Console script for lettuce."""

import sys
import click
import torch
import numpy as np

import lettuce
from lettuce import BGKCollision, StandardStreaming, Lattice, LatticeOfVector
from lettuce import D2Q9, TaylorGreenVortex2D, Simulation, ErrorReporter


@click.group()
@click.version_option(version=lettuce.__version__)
@click.option("--cuda/--no-cuda", default=True, help="Use cuda (default=True).")
@click.option("-i", "--gpu-id", type=int, default=0, help="Device ID of the GPU (default=0).")
@click.option("-p", "--precision", type=click.Choice(["half", "single", "double"]), default="single",
              help="Numerical Precision; 16, 32, or 64 bit per float (default=single).")
@click.option("--lov/--no-lov", default=False, help="Use lattice-of-vector data storage order.")
@click.pass_context  # pass parameters to sub-commands
def main(ctx, cuda, gpu_id, precision, lov):
    """Pytorch-accelerated Lattice Boltzmann Solver
    """
    ctx.obj = {'device': None, 'dtype': None, 'lov': None}
    if cuda:
        if not torch.cuda.is_available():
            print("CUDA not found.")
            raise click.Abort
        device = torch.device("cuda:{}".format(gpu_id))
    else:
        device = torch.device("cpu")
    dtype = {"half": torch.half, "single": torch.float, "double": torch.double}[precision]

    ctx.obj['device'] = device
    ctx.obj['dtype'] = dtype
    ctx.obj['lov'] = lov


@main.command()
@click.option("-s", "--steps", type=int, default=10, help="Number of time steps.")
@click.option("-r", "--resolution", type=int, default=1024, help="Grid Resolution")
@click.option( "--profile/--no-profile", default=False, help="Whether to write profiling information (default=False).")
@click.pass_context  # pass parameters to sub-commands
def benchmark(ctx, steps, resolution, profile):
    """Run a short simulation and print performance in MLUPS.
    """
    device, dtype, lov = ctx.obj['device'], ctx.obj['dtype'], ctx.obj['lov']
    if lov:
        lattice = LatticeOfVector(D2Q9, device, dtype)
    else:
        lattice = Lattice(D2Q9, device, dtype)
    flow = TaylorGreenVortex2D(resolution=resolution, reynolds_number=1, mach_number=0.05, lattice=lattice)
    collision = BGKCollision(lattice, tau=flow.units.relaxation_parameter_lu)
    streaming = StandardStreaming(lattice)
    simulation = Simulation(flow=flow, lattice=lattice,  collision=collision, streaming=streaming)
    mlups = simulation.step(num_steps=steps)

    click.echo("Finished {} steps in {} bit precision. MLUPS: {:10.2f}".format(
        steps, str(dtype).replace("torch.float",""), mlups))
    if profile:
        pass
    #TODO: write profiling information
    return 0


@main.command()
@click.pass_context
def convergence(ctx):
    """Use Taylor Green 2D for convergence test in diffusive scaling."""
    device, dtype, lov = ctx.obj['device'], ctx.obj['dtype'], ctx.obj['lov']
    if lov:
        lattice = LatticeOfVector(D2Q9, device, dtype)
    else:
        lattice = Lattice(D2Q9, device, dtype)
    error_u_old = None
    error_p_old = None
    print(("{:>15} " * 5).format("resolution", "error (u)", "order (u)", "error (p)", "order (p)"))

    for i in range(4,9):
        resolution = 2**i
        mach_number = 8/resolution

        # Simulation
        flow = TaylorGreenVortex2D(resolution=resolution, reynolds_number=10000, mach_number=mach_number, lattice=lattice)
        collision = BGKCollision(lattice, tau=flow.units.relaxation_parameter_lu)
        streaming = StandardStreaming(lattice)
        simulation = Simulation(flow=flow, lattice=lattice, collision=collision, streaming=streaming)
        error_reporter = ErrorReporter(lattice, flow, interval=1, out=None)
        simulation.reporters.append(error_reporter)
        simulation.step(num_steps=10*resolution)

        # error calculation
        error_u, error_p = np.mean(error_reporter.out, axis=0).tolist()
        factor_u = 0 if error_u_old is None else error_u_old / error_u
        factor_p = 0 if error_p_old is None else error_p_old / error_p
        error_u_old = error_u
        error_p_old = error_p
        print("{:15} {:15.2e} {:15.1f} {:15.2e} {:15.1f}".format(
            resolution, error_u, factor_u/2, error_p, factor_p/2))
    return 0


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover

