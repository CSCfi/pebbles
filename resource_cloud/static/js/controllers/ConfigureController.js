app.controller('ConfigureController', ['$q', '$scope', '$http', '$interval', 'AuthService', 'Restangular',
                              function ($q,   $scope,   $http,   $interval,   AuthService,   Restangular) {

        Restangular.setDefaultHeaders({token: AuthService.getToken()});

        var plugins = Restangular.all('plugins');

        plugins.getList().then(function (response) {
            $scope.plugins = response;
        });

        var blueprints = Restangular.all('blueprints');

        blueprints.getList({show_deactivated: true}).then(function (response) {
            $scope.blueprints = response;
        });

        $scope.submitForm = function(form, model) {
            if (form.$valid) {
                blueprints.post({ plugin: $scope.selectedPlugin.id, name: model.name, config: model }).then(function (response) {
                        blueprints.getList({show_deactivated: true}).then(function (response) {
                                $scope.blueprints = response;
                            }
                        )
                    }
                );
                $('#blueprintCreate').modal('hide')
            }
        }
        $scope.updateBlueprint = function (form, model) {
            if (form.$valid) {
                $scope.selectedBlueprint.config = model;
                $scope.selectedBlueprint.put().then(function (response) {
                        blueprints.getList({show_deactivated: true}).then(function (response) {
                                $scope.blueprints = response;
                            }
                        )
                    }
                );
                $('#blueprintConfig').modal('hide')
            }
        }

        $scope.selectPlugin = function(plugin) {
            $scope.selectedPlugin = plugin;
            $scope.$broadcast('schemaFormRedraw');
        }

        $scope.selectBlueprint = function(blueprint) {
            $scope.selectedBlueprint = blueprint;
            $scope.$broadcast('schemaFormRedraw');
        }

        $scope.createBlueprint = function() {
            var newBlueprint = {};
            newBlueprint.name = $scope.name;
            newBlueprint.config = $scope.config;
            newBlueprint.plugin = $scope.plugin;
            blueprints.post(newBlueprint);
        }

        $scope.updateConfig = function() {
            $scope.selectedBlueprint.put();
            $('#blueprintConfig').modal('hide')

        }

        

        $scope.activate = function (blueprint) {
            blueprint.is_enabled = true;
            blueprint.put();
        }

        $scope.deactivate = function (blueprint) {
            blueprint.is_enabled = undefined;
            blueprint.put();
        }

    }]);
