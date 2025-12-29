import click

from mlip_autopipec.orchestrator_cycle01 import run_cycle01_workflow


@click.command()
@click.option(
    "--config",
    "config_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to the Cycle 01 YAML configuration file.",
)
@click.option(
    "--structure",
    "structure_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to the input atomic structure file (e.g., .xyz, .cif).",
)
def main(config_path: str, structure_path: str):
    """
    Command-line interface to run the MLIP-AutoPipe Cycle 01 workflow.

    This tool takes a configuration file and a structure file as input,
    runs the automated DFT labelling, and then trains a basic MLIP model.
    """
    run_cycle01_workflow(config_path, structure_path)


if __name__ == "__main__":
    main()
