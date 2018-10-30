app.controller('BlueprintsController', ['$q', '$scope', '$http', '$interval', '$uibModal', 'AuthService', 'Restangular',
                              function ($q,   $scope,   $http,   $interval,   $uibModal,   AuthService,   Restangular) {

        $scope.isAdmin = function() {
            return AuthService.isAdmin();
        };

        $scope.getIcons = function() {
            return AuthService.getIcons()[3];
        };

        Restangular.setDefaultHeaders({token: AuthService.getToken()});

        var templates = Restangular.all('blueprint_templates');

        templates.getList().then(function (response) {
            $scope.templates = response;
        });

        var blueprints = Restangular.all('blueprints');

        blueprints.getList({show_deactivated: true}).then(function (response) {
            $scope.blueprints = response;
        });

	var instances = Restangular.all('instances');

         var groups = Restangular.all('groups');

         groups.getList().then(function (response) {
             $scope.groups = response;
         });

        var importExportBlueprints = Restangular.all('import_export/blueprints');

        $scope.exportBlueprints = function () {

            importExportBlueprints.getList().then(function(response) {

                var jsonStr = JSON.stringify(response, null, 2); // Pretty print

                var blob = new Blob([jsonStr], {type: 'application/json'});
                var anchorLink = document.createElement('a');
                var mouseEvent = new MouseEvent('click');

                anchorLink.download = "blueprints.json";
                anchorLink.href = window.URL.createObjectURL(blob);
                anchorLink.dataset.downloadurl = ['text/json', anchorLink.download, anchorLink.href].join(':');
                anchorLink.dispatchEvent(mouseEvent);
            });
        };

        $scope.openImportBlueprintsDialog = function() {
            $uibModal.open({
                templateUrl: '/partials/modal_import_blueprints.html',
                controller: 'ModalImportBlueprintsController',
                resolve: {
                    importExportBlueprints: function() {
                        return importExportBlueprints;
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

        $scope.openCreateBlueprintDialog = function(template) {
            $uibModal.open({
                templateUrl: '/partials/modal_create_blueprint.html',
                controller: 'ModalCreateBlueprintController',
                resolve: {
                    template: function() {
                        return template;
                    },
                    blueprints: function() {
                        return blueprints;
                    },
                    groups_list: function() {
                        return $scope.groups;
                    }
                }
            }).result.then(function() {
                blueprints.getList().then(function (response) {
                    $scope.blueprints = response;
                });
            });
        };

        $scope.openReconfigureBlueprintDialog = function(blueprint) {
            blueprint.get().then(function(response){
                $uibModal.open({
                    templateUrl: '/partials/modal_reconfigure_blueprint.html',
                    controller: 'ModalReconfigureBlueprintController',
                    resolve: {
                        blueprint: function() {
                             return blueprint;
                        },
                        groups_list: function() {
                             return $scope.groups;
                        }
                    }
                }).result.then(function() {
                     blueprints.getList().then(function (response) {
                         $scope.blueprints = response;
                     });
                 });
            }, function (response) {
                 if(response.status == 422) {
                     $.notify({title: 'HTTP ' + response.status,  message: " Cannot reconfigure blueprint."}, {type: 'danger'});
                 }
           });
        };

        $scope.openBlueprintLinkDialog = function(blueprint) {
            blueprint.get().then(function(response){
                $uibModal.open({
                     size: 'lg',
                     templateUrl: '/partials/modal_url.html',
                     controller: 'ModalBlueprintUrlController',
                     resolve: {
                        blueprint: blueprint
                     }
                });
           }, function(response) {
                 if(response.status == 422) {
                     $.notify({title: 'HTTP ' + response.status, message: " Cannot get the link for blueprint."}, {type: 'danger'});
                 }
           });
        };

        $scope.copyBlueprint = function(blueprint) {
            var blueprint_copy = Restangular.all('blueprints').one('blueprint_copy', blueprint.id).put();
            blueprint_copy.then(function () {
                blueprints.getList().then(function (response) {
                      $.notify({
                          title: 'Success: ',
                          message: 'A copy of the blueprint was made'
                          }, {type: 'success'});
                    $scope.blueprints = response;
                });
            }, function (response) {
                   if(response.status == 422) {
                       $.notify({
                           title: 'HTTP ' + response.status,
                           message: 'Cannot copy blueprint'
                       }, {type: 'danger'});
                   }
           });
        }, function (response) {
               $.notify({
                   title: 'HTTP ' + response.status,
                   message: 'Could not copy blueprint'
               }, {type: 'danger'});

        }

        $scope.archiveBlueprint = function(blueprint) {
             blueprint.current_status = 'archived';
             blueprint.patch().then(function() {
                blueprints.getList().then(function (response) {
                     $scope.blueprints = response;
                 });
            });
        };
    
	$scope.deleteBlueprint = function(blueprint) {
            blueprint.get().then(function(response){ 
	        instances.getList().then(function (response) {
		     var blueprint_instances = _.filter(response,function(user) { return user.blueprint_id === blueprint.id });
                     $uibModal.open({
		         templateUrl: 'partials/modal_check_running_instance_confirm.html',
		         controller: 'ModalDeleteBlueprintsController',
		         size: 'sm',
		         resolve: {
			     blueprint: function() {
			         return blueprint;
			     },
                             blueprint_instances: function() {
                                 return blueprint_instances;
                             }
		         }
		     }).result.then(function() {
                         blueprints.getList().then(function (response) {
                            $scope.blueprints = response;
                         });
		     });
                });
            }, function (response) {
                     $.notify({title: 'HTTP ' + response.status, message: " Cannot delete blueprint."}, {type: 'danger'});
            });
        };

 

        $scope.deleteNotification = function(notification) {
            notification.remove().then(function() {
                updateNotificationList();
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
            blueprint.get().then(function (response) {
                blueprint.is_enabled = true;
                blueprint.put();
            }, function(response) {
                if (response.status == 422) {
                     $.notify({title: 'HTTP ' + response.status, message: 'Cannot activate blueprint'}, {type: 'danger'});
                }
            });
        };

        $scope.deactivate = function (blueprint) {
            blueprint.get().then(function () {
                blueprint.is_enabled = undefined;
                blueprint.put();
            }, function(response) {
                if (response.status == 422) {
                     $.notify({title: 'HTTP ' + response.status, message: 'Cannot deactivate blueprint'}, {type: 'danger'});
                }
            });
        };

    }]);



app.controller('ModalImportBlueprintsController', function($scope, $modalInstance, importExportBlueprints, blueprints)
{

    $scope.importBlueprints = function(element) {

        $scope.isImportSuccess = false;
        $scope.isImportFailed = false;
        var errorResponse = "Indexes of blueprints which were not imported: ";
        var requestsCount = 0;
        var file = element.files[0];
        var reader = new FileReader();
        reader.onload = function() {
            $scope.$apply(function() {
                try {
                    // Read from the file and convert to JSON object
                    var blueprintsJson = JSON.parse(String(reader.result));
                    var totalItems = blueprintsJson.length;
                    for (var blueprintIndex in blueprintsJson) {
                        if (blueprintsJson.hasOwnProperty(blueprintIndex)) {
                            var blueprintItem = blueprintsJson[blueprintIndex];
                            var obj = {
                                name: blueprintItem.name,
                                config: blueprintItem.config,
                                template_name: blueprintItem.template_name,
                                group_name: blueprintItem.group_name,
                                index: blueprintIndex
                            };  // Send according to forms defined

                            importExportBlueprints.post(obj).then(function () {  // Post to the REST API
                                requestsCount++;
                                $scope.imported = true;
                                if (requestsCount == totalItems) {  // Check if all the requests were OK
                                    $scope.isImportSuccess = true;
                                }
                            }, function (response) {
                                 // Attach the indices of blueprint items which are corrupt
                                errorResponse = errorResponse + response.config.data.index + ' ';
                                $.notify({
                                    title: 'HTTP ' + response.status,
                                    message: 'error:' + response.statusText
                                }, {type: 'danger'});
                                $scope.isImportFailed = true;
                                $scope.errorResponse = errorResponse;
                            });
                        }
                    }
                    if(totalItems == 0){
                        $.notify({
                                    title: 'Blueprints could not be imported!',
                                    message: 'No blueprints found'
                                }, {type: 'danger'});
                    }
                }
                catch(exception){
                    $.notify({
                        title: 'Blueprints could not be imported!',
                        message: exception
                    }, {type: 'danger'});
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


app.controller('ModalCreateBlueprintController', function($scope, $modalInstance, template, blueprints, groups_list) {
    $scope.template = template;
    $scope.groups = groups_list;
    $scope.createBlueprint = function(form, model, groupModel) {
    $scope.$broadcast('schemaFormValidate');
        if (form.$valid) {
            blueprints.post({ template_id: $scope.template.id, name: model.name, config: model, group_id:  groupModel}).then(function () {
                $modalInstance.close(true);
            }, function(response) {
                $.notify({title: 'HTTP ' + response.status, message: 'unable to create blueprint'}, {type: 'danger'});
            });
        }
    };

    $scope.cancel = function() {
        $modalInstance.dismiss('cancel');
    };
});

app.controller('ModalReconfigureBlueprintController', function($scope, $modalInstance, blueprint, groups_list) {
    $scope.blueprint = blueprint;
    var config_mismatch = false;
    blueprint.get().then(function(response){
        if(!_.isEqual($scope.blueprint['config'], response['config'])){  // Object equality check
            alert('Blueprint configuration has been changed from the previous configuration');
            $scope.blueprint = response;
            config_mismatch = true; //Concurrency
        }
    });
    //$scope.groups = groups_list;
    //$scope.groupModel =  _.filter(groups_list, {'id': blueprint.group_id})[0];
    //$scope.updateBlueprint = function(form, model, groupModel) {
    $scope.updateBlueprint = function(form, model) {
        if (form.$valid) {
            $scope.blueprint.config = model;
            //$scope.blueprint.group_id = groupModel.id;
            $scope.blueprint.put().then(function () {
                $modalInstance.close(true);
            }, function(response) {
                $.notify({title: 'HTTP ' + response.status, message: 'unable to reconfigure blueprint'}, {type: 'danger'});
            });
        }
    };

    
    $scope.cancel = function() {
        if(config_mismatch){
            $modalInstance.close(true);  // launches the result section of modal
        }
        $modalInstance.dismiss('cancel');  // does not launch the result of modal
    };
});

app.controller('ModalBlueprintUrlController', function($scope, $modalInstance, blueprint) {

    $scope.url_type = "Blueprint Link (To be given to the users)" + ' - ' + blueprint.name;
    var hostname = window.location.hostname;
    $scope.url = 'https://' + hostname + '/#/blueprint/' + blueprint.id;

    $scope.cancel = function() {
        $modalInstance.dismiss('cancel');
    };
});


app.controller('ModalDeleteBlueprintsController', function($scope, $modalInstance, blueprint, blueprint_instances) {
     $scope.blueprint_instances = blueprint_instances;
     $scope.removeBlueprints = function() {
          blueprint.remove().then(function () {
               $.notify({message: "Blueprint: " + blueprint.name + " is successfully deleted"}, {type: 'success'});
               $modalInstance.close(true);
               }, function(response) {
                     $.notify({title: 'HTTP ' + response.status, message: 'Unable to delete the blueprint: ' + blueprint.name}, {type: 'danger'});
                     $modalInstance.close(true);
          });
     };

     $scope.cancel = function() {
          $modalInstance.dismiss('cancel');
     };
});
