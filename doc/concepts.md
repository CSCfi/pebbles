# Pebbles Concepts

This document defines concepts in Pebbles software.

## Service and software

### Pebbles

- Open source software powering Notebooks.csc.fi service

### Notebooks aka Notebooks.csc.fi

- CSC service for interactive web based applications

## Core concepts

### Application

- Predefined content for one learning session
- Usually a Docker container - either JupyterLab or RStudio
- Created by Workspace manager based on Application template

### ApplicationSession

- One running copy of an Application
- Owned by user
- Has lifetime set by Application

### Workspace

- A collection of Applications and Users.
- Has an owner
- May have managers
- Has a lifetime
- May contain shared Persistent Workspace data
- May contain Persistent User data

### Persistent user data

- A persistent directory, storing data between application session launches
- Available in the application session in a directory configured by Workspace manager
- Is tied to a workspace
- Has lifetime tied to a Workspace

### Workspace data

- Shared data directory available to all users in a Workspace
- Is writable by Workspace manager
- Is tied to a workspace
- Has lifetime tied to a Workspace

### Application template

- A template for Applications
- Created by Admin
- Tied to a Cluster
- Has attributes needed by Cluster
- Has attributes selected for customization per Application

## Roles

### End user

- A workspace participant or a user of public Applications
- Is authenticated
- May launch application sessions
- Has access to public Applications
- May be part of Workspaces
- Has access to Workspace Applications through membership

### Workspace owner

- Principal of the Workspace
- May add managers
- Acts as a manager

### Workspace manager (Assistant?)

- May add users
- May add Applications based on Applications templates

### Admin

- System administrator
- Has full rights in the system

## System concepts

### Cluster

- A resource for executing the application sessions
- In practice: some sort of Kubernetes cluster
- Configured by Admin

### Provisioning driver

- Software component that takes care of running application sessions in a Cluster
