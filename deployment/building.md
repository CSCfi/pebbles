# Building pebbles image

Build the docker image using pebbles dockerfile from the project root directory:

```shell script
docker build --tag pebbles:latest . --file=deployment/pebbles.Dockerfile
```

For deployment, see `pebbles-deploy` project.
