# Development container

Open this repository in VS Code and choose **Dev Containers: Reopen in
Container**. The development target installs uv and all dependency groups; the
repository is bind-mounted by the Dev Containers extension.

The container intentionally contains no PyBDSF, LSMTool, or Rapthor runtime.
Equivalence and end-to-end tests should use explicit integration environments
described in the source-finder implementation plan.
