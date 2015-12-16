app.controller('ConfigureController', ['$q', '$scope', '$http', '$interval', '$uibModal', 'AuthService', 'Restangular',
                              function ($q,   $scope,   $http,   $interval,   $uibModal,   AuthService,   Restangular) {

        Restangular.setDefaultHeaders({token: AuthService.getToken()});

        var plugins = Restangular.all('plugins');

        plugins.getList().then(function (response) {
            $scope.plugins = response;
        });

        var blueprints = Restangular.all('blueprints');

        blueprints.getList({show_deactivated: true}).then(function (response) {
            $scope.blueprints = response;
        });

        var variables = Restangular.all('variables');
        variables.getList().then(function (response) {
            $scope.variables = response;
        });

        var import_export = Restangular.all('import_export');

        $scope.downloadFile = function () {

            import_export.getList().then(function(response) {

            json_str = JSON.stringify(response, undefined, 2);

            var blob = new Blob([json_str], {type: 'application/json'}),
            mouse_event = document.createEvent('MouseEvents'),
            anchor_link = document.createElement('a');

            anchor_link.download = "blueprints.json";
            anchor_link.href = window.URL.createObjectURL(blob);
            anchor_link.dataset.downloadurl = ['text/json', anchor_link.download, anchor_link.href].join(':');
            mouse_event.initMouseEvent('click', true, false, window,
            0, 0, 0, 0, 0, false, false, false, false, 0, null);
            anchor_link.dispatchEvent(mouse_event);
            });
        };

         $scope.open_import_blueprints_dialog = function() {
            var modalImportBlueprints = $uibModal.open({
                templateUrl: '/partials/modal_import_blueprints.html',
                controller: 'ModalImportBlueprintsController',
                resolve: {
                    import_export: function() {
                        return import_export;
                    },
                    blueprints: function() {
                        return blueprints;
                    }
               }
            }).result.then(function() {
                   blueprints.getList().then(function (response) {
                   $scope.blueprints = response;
                   });
               });
        };


        $scope.open_create_blueprint_dialog = function(plugin) {
            var modalCreateBlueprint = $uibModal.open({
                templateUrl: '/partials/modal_create_blueprint.html',
                controller: 'ModalCreateBlueprintController',
                resolve: {
                    plugin: function() {
                        return plugin;
                    },
                    blueprints: function() {
                        return blueprints;
                    }
                }
            }).result.then(function() {
                blueprints.getList().then(function (response) {
                    $scope.blueprints = response;
                });
            });
        };

        $scope.open_reconfigure_blueprint_dialog = function(blueprint) {
            var modalReconfigureBlueprint = $uibModal.open({
                templateUrl: '/partials/modal_reconfigure_blueprint.html',
                controller: 'ModalReconfigureBlueprintController',
                resolve: {
                    blueprint: function() {
                        return blueprint;
                    }
                }
            }).result.then(function() {
                blueprints.getList().then(function (response) {
                    $scope.blueprints = response;
                });
            });
        };

        $scope.selectBlueprint = function(blueprint) {
            $scope.selectedBlueprint = blueprint;
            $scope.$broadcast('schemaFormRedraw');
        };

        $scope.updateConfig = function() {
            $scope.selectedBlueprint.put();
            $('#blueprintConfig').modal('hide');
        };

        $scope.activate = function (blueprint) {
            blueprint.is_enabled = true;
            blueprint.put();
        };

        $scope.deactivate = function (blueprint) {
            blueprint.is_enabled = undefined;
            blueprint.put();
        };

        $scope.updateVariable = function(variable) {
            variable.put().then(function() {
                // refresh list to see server side applied transformations (for ex. 'dsfg' -> False)
                variables.getList().then(function (response) {
                    $scope.variables = response;
                });
            }).catch(function(response) {
                if (response.status == 409) {
                    $.notify({title: 'HTTP ' + response.status, message: response.data.error}, {type: 'danger'});
                }
                variables.getList().then(function (response) {
                    $scope.variables = response;
                });
            });
        };
    }]);



app.controller('ModalImportBlueprintsController', function($scope, $modalInstance, import_export, blueprints) {

     $scope.uploadFile = function(element) {

         $scope.isImportSuccess = false;
         $scope.isImportFailed = false;
         var errorResponse = "Indexes of blueprints which were not imported: ";
         var requestsCount = 0;

         file = element.files[0];
         var reader = new FileReader();
         reader.onload = function(e) {
         $scope.$apply(function() {
             $scope.test = reader.result;

             blueprints_json = JSON.parse(reader.result);  // Read from the file and convert to JSON object
             total_items = blueprints_json.length;

             for (blueprint_index in blueprints_json) {

                 blueprint_item = blueprints_json[blueprint_index];
                 obj = {name: blueprint_item.name, config: blueprint_item.config, plugin_name: blueprint_item.plugin_name, index: blueprint_index};  // Send according to forms defined
                 import_export.post(obj).then(function () {  // Post to the REST API
                      requestsCount++;
                      $scope.imported = true;
                      if(requestsCount == total_items){  // Check if all the requests were OK
                          $scope.isImportSuccess = true;
                      }
                 }, function(response) {
                     errorResponse = errorResponse + response.config.data.index + ' ';  // Attach the indices of blueprint items which are corrupt
                     $.notify({title: 'HTTP ' + response.status, message: 'error:' + response.statusText}, {type: 'danger'});
                     $scope.isImportFailed = true;
                     $scope.errorResponse = errorResponse;
                    });
              }

              });
          };

         reader.readAsText(file);  // Fires the onload event defined above
    };

    $scope.done = function() {
         $modalInstance.close(true);
    };

    $scope.cancel = function() {
        $modalInstance.dismiss('cancel');
    };

});


app.controller('ModalCreateBlueprintController', function($scope, $modalInstance, plugin, blueprints) {
    $scope.plugin = plugin;
    $scope.createBlueprint = function(form, model) {
        if (form.$valid) {
            blueprints.post({ plugin: $scope.plugin.id, name: model.name, config: model }).then(function () {
                $modalInstance.close(true);
            }, function() {
                $.notify({title: 'HTTP ' + response.status, message: 'unable to create blueprint'}, {type: 'danger'});
            });
        }
    };

    $scope.cancel = function() {
        $modalInstance.dismiss('cancel');
    };
});

app.controller('ModalReconfigureBlueprintController', function($scope, $modalInstance, blueprint) {
    $scope.blueprint = blueprint;
    $scope.updateBlueprint = function(form, model) {
        if (form.$valid) {
            $scope.blueprint.config = model;
            $scope.blueprint.put().then(function () {
                $modalInstance.close(true);
            }, function(response) {
                $.notify({title: 'HTTP ' + response.status, message: 'unable to reconfigure blueprint'}, {type: 'danger'});
            });
        }
    };

    $scope.cancel = function() {
        $modalInstance.dismiss('cancel');
    };
});
