app.controller('ConfigureController', ['$q', '$scope', '$interval', 'AuthService', 'Restangular',
                              function ($q,   $scope,   $interval,   AuthService,   Restangular) {

        Restangular.setDefaultHeaders({token: AuthService.getToken()});

        var plugins = Restangular.all('plugins');

        plugins.getList().then(function (response) {
            $scope.plugins = response;
        });

        var resources = Restangular.all('resources');

        resources.getList({show_deactivated: true}).then(function (response) {
            $scope.resources = response;
        });

        $scope.create = function () {
            resources.post({ plugin: $scope.plugin, name: $scope.name, config: $scope.config }).then(function (response) {
                    resources.getList({show_deactivated: true}).then(function (response) {
                            $scope.resources = response;
                        }
                    )
                }
            );
            $('#resourceCreate').modal('hide')
        }

        var currentResource = null;

        $scope.selectResource = function(resource) {
            currentResource = resource;
            $scope.name = currentResource.name;
            $scope.config = currentResource.config;
            $scope.plugin = currentResource.plugin;
        }

        $scope.createResource = function() {
            currentResource.name = $scope.name;
            currentResource.config = $scope.config;
            currentResource.plugin = $scope.plugin;
            resources.post(currentResource);
        }

        $scope.updateConfig = function() {
            currentResource.name = $scope.name;
            currentResource.plugin = $scope.plugin;
            currentResource.config = $scope.config;
            currentResource.put();
            $('#resourceConfig').modal('hide')

        }

        $scope.activate = function (resource) {
            resource.is_enabled = true;
            resource.put();
        }

        $scope.deactivate = function (resource) {
            resource.is_enabled = undefined;
            resource.put();
        }

    }]);
