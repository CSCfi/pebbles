/* global app */
app.controller('DashboardController', ['$q', '$scope', '$routeParams', '$timeout', '$interval', 'AuthService', '$uibModal', 'Restangular', 'isUserDashboard', 'DesktopNotifications',
                              function ($q,   $scope,   $routeParams, $timeout, $interval,   AuthService,  $uibModal,  Restangular,   isUserDashboard, DesktopNotifications) {
        // used only to get admin dashboard
        $scope.getIcons = function() {
            if (AuthService.getIcons()) {
                return AuthService.getIcons()[3];
            }
            else {
                return false;
            }
        };

        Restangular.setDefaultHeaders({token: AuthService.getToken()});
        var LIMIT_DEFAULT = 100, OFFSET_DEFAULT=0;
        $scope.currentView = "default";

        $scope.toggleClass = function(view){
            if ($scope.currentView == view){
                return "active";
            }
            return undefined;
        }
        $scope.isCurrentView = function(view){
            if ($scope.currentView == view){
                return true;
            }
            
            return false;
        }

        var workspace_join = Restangular.all('workspaces').one('workspace_join');

        var environments = Restangular.all('environments');
        environments.getList().then(function (response) {
            if($routeParams.environment_id){  // Case when the environment link is given
                var environment_id = $routeParams.environment_id;
                $scope.environments = _.filter(response, { 'id': environment_id });
                if (!$scope.environments.length){
                     $uibModal.open({
                     templateUrl: '/partials/modal_workspace_join.html',
                     controller: 'ModalWorkspaceJoinController',
                     size: 'sm',
                     backdrop  : 'static',
                     keyboard  : false,
                     resolve: {
                         workspace_join: function() {
                             return workspace_join;
                         },
                         join_title: function(){
                             return "Enter the join code"
                         },
                         dismiss_reason: function(){
                             return "You need to join a valid workspace to see the environment"
                         }
                     }
                     }).result.then(function() {
                         refresh_environments_for_link(environment_id);
                     });
                }
            }
            else{  // Fetch all environments
                $scope.environments = response;
            }
        });

        var refresh_environments_for_link = function(environment_id){
            environments.getList().then(function (response) {
            $scope.environments = _.filter(response, {'id': environment_id, 'is_enabled': true });
            if(!$scope.environments.length){
                $.notify({
                    title: "INVALID LINK!", message: "The link provided appears to be invalid. Could not retrieve any information."}, {type: "danger"});
            }
            });
        }

        var instances = Restangular.all('instances');

        var limit = undefined, offset = undefined, include_deleted = undefined;

        $scope.limit = LIMIT_DEFAULT;
        $scope.offset = OFFSET_DEFAULT;

        $scope.markedInstances = {};
        $scope.noMarkedInstances = function() {
             return _.isEmpty($scope.markedInstances);
        };
        $scope.isMarked = function(instance){
            if(instance.id in $scope.markedInstances){
                 return true;
            }
            return false;
        };
        $scope.markInstance = function(marked, instance) {
             if (marked){
                  $scope.markedInstances[instance.id] = instance;
             }
             else{
                  delete $scope.markedInstances[instance.id];
             }
        };
        $scope.markAll = function() {
           if ($scope.checkAll){
               var scoped_instances = $scope.instances;
               for (i_index in scoped_instances){
                   if(isNaN(parseInt(i_index))){
                       continue;
                   }
                   instance = scoped_instances[i_index]
                   $scope.markedInstances[instance.id] = instance;
               }
           }
           else{
               $scope.markedInstances = {};
           }
        };


        $scope.updateInstanceList = function(option) {
            var queryParams = {};
            if (include_deleted) {
                queryParams.show_deleted = true;
            }
            if (limit) {
                queryParams.limit = $scope.limit;
            }
            if (offset) {
                queryParams.offset = $scope.offset;
            }
            if (AuthService.isWorkspaceOwnerOrAdmin() && isUserDashboard) {
		queryParams.show_only_mine = true;
            }
            instances.getList(queryParams).then(function (response) {
                if ($scope.checkAll){
                    new_instances = _.differenceBy(response, $scope.instances, 'id');
                    for (new_instance_index in new_instances){
                        new_instance = new_instances[new_instance_index];
                        $scope.markedInstances[new_instance.id] = new_instance;
                    }
                }
                $scope.instances = response;
            });
            var own_instances = _.filter($scope.instances, {'user_id': AuthService.getUserId(), 'state': 'running'});
	    DesktopNotifications.notifyInstanceLifetime(own_instances);
        };

        $scope.toggleAdvancedOptions = function() {
            $scope.showAdvancedOptions = ! $scope.showAdvancedOptions;
            if (! $scope.showAdvancedOptions) {
                $scope.resetFilters();
            }
        };

        $scope.applyFilters = function() {
            include_deleted = $scope.include_deleted;
            limit = $scope.limit;
            offset = $scope.offset;
            $scope.updateInstanceList();
        };

        $scope.resetFilters = function() {
            $scope.include_deleted = false;
            $scope.limit = LIMIT_DEFAULT;
            $scope.offset = OFFSET_DEFAULT;
            $scope.query = undefined;
            limit = offset = include_deleted = undefined;
            $scope.updateInstanceList();
        };

        $scope.updateInstanceList();

        $scope.maxInstanceLimitReached = function(environment) {
            var max_instance_limit = environment.full_config['maximum_instances_per_user'];
            var own_instances = _.filter($scope.instances, {'user_id': AuthService.getUserId()});
            var instance_counts = _.countBy(own_instances, 'environment_id');
            var running_instances = instance_counts[environment.id];
            if (typeof running_instances == 'undefined') {
                running_instances = 0;
            }
            if (running_instances < max_instance_limit) {
                return false;
            }
            return true;
        };

        $scope.showMaxInstanceLimitInfo = function() {
            $.notify({title: 'LAUNCH BUTTON DISABLED : ', message: 'Maximum number of running instances for the selected environment reached'}, {type: 'danger'});
        }

        $scope.provision = function (environment) {
            instances.post({environment: environment.id}).then(function (response) {
                $scope.updateInstanceList();
                //Check if the instance is still in queueing state after 10 mins, if so send email to admins. 
                $timeout(function () {
                    Restangular.one('instances', response.id).get().then(function (response) {
                       if (response.state != "running") {
                          Restangular.one('instances', response.id).customPOST({'send_email': true}).then(function (response) {
                          });
                          // Prob encountered only in queuing state
                          if(response.state == "queueing") {
                              response.remove().then(function (res) {
                                 $scope.updateInstanceList();
                              });
                          }
                       }
                    });
                }, 600000);
            }, function(response) {
                if (response.status != 409) {
                    $.notify({title: 'HTTP ' + response.status, message: 'unknown error'}, {type: 'danger'});
                } else {
                    if (response.data.error == 'USER_OVER_QUOTA') {
                        $.notify({title: 'HTTP ' + response.status, message: 'User quota exceeded, contact your administrator in order to get more'}, {type: 'danger'});
                    } else if (response.data.error == 'USER_BLOCKED') {
                        $.notify({title: 'HTTP ' + response.status, message: 'You have been blocked, contact your administrator'}, {type: 'danger'});
                    } else {
                        $.notify({title: 'HTTP ' + response.status, message: 'Maximum number of running instances for the selected environment reached.'}, {type: 'danger'});
                    }
                }
            });
        };

        $scope.deprovision = function (instance) {
            instance.state = 'deleting';
            instance.error_msg = '';
            instance.remove().then(function (r) {
                $scope.updateInstanceList();
        });
            if (instance.id in $scope.markedInstances){
                delete $scope.markedInstances[instance.id];
            }
        };

        $scope.openInBrowser = function(instance) {
            if('password' in instance.instance_data){
                $uibModal.open({
                    templateUrl: '/partials/modal_show_password.html',
                    controller: 'ModalShowPasswordController',
                    scope: $scope,
                    resolve: {
                        instance: function(){
                           return instance;
                        },

                        environment: function(){
                           return _.filter($scope.environments, { 'id': instance.environment_id });
                        },
                    }   
                }).result.then(function(markedInstances) {
                       window.open(instance.instance_data['endpoints'][0].access, '_blank');
                });
            }
            else{
                window.open(instance.instance_data['endpoints'][0].access, '_blank');
            }
        };


        $scope.openDestroyDialog = function(instance) {
            $uibModal.open({
                templateUrl: '/partials/modal_destroy_instance.html',
                controller: 'ModalDestroyInstanceController',
                scope: $scope,
                resolve: {
                    instance: function(){
                       return instance;
                    },
                    markedInstances: function(){
                       return $scope.markedInstances;
                    }
               }
            }).result.then(function(markedInstances) {
               $scope.markedInstances = markedInstances;
            });
        };


        $scope.isAdmin = function() {
            return AuthService.isAdmin();
        };

        var stop;
        $scope.startPolling = function() {
            if (angular.isDefined(stop)) {
                return;
            }
            stop = $interval(function () {
                if (AuthService.isAuthenticated()) {
                    $scope.updateInstanceList();
                } else {
                    $interval.cancel(stop);
                }
            }, 10000);
        };

        $scope.stopPolling = function() {
            if (angular.isDefined(stop)) {
                $interval.cancel(stop);
                stop = undefined;
            }
        };

        $scope.$on('$destroy', function() {
            $scope.stopPolling();
        });

        $scope.filterOddEven = function(index, choice) {
            index++;
            if (choice == 1) {
                return index % 2 == 1;
            }
            else {
                return index % 2 != 1;
            }
        };

        $scope.oddEvenRange = function() {
            var arr = [1, 2];
            return arr;
        };

        $scope.startPolling();
    }]);

app.controller('ModalShowPasswordController', function($scope, $modalInstance, instance, environment) {
    $scope.instance = instance;
    $scope.environment = environment;
    $scope.copyAndClose = function() {
        try {
            var passwordField = document.querySelector('#password');
            passwordField.select();
            document.execCommand('copy');
        }
        catch (e) {
            console.log(e);
        }
        $modalInstance.close(true);
    };
});

app.controller('ModalDestroyInstanceController', function($scope, $modalInstance, instance, markedInstances) {

    $scope.instance = instance;
    $scope.destroyMultipleInstances = function() {
        if (instance == null){
            return true;
        }
            return false;
        
    }

    var deprovision = function (instance) {
        instance.state = 'deleting';
        instance.error_msg = '';
        instance.remove().then(function (r) {
                $scope.updateInstanceList();
        });
        if (instance.id in markedInstances){
            delete markedInstances[instance.id];
        }
    };

    var destroySelected = function() {
        for (mi_index in markedInstances){
            deprovision(markedInstances[mi_index]);
        }
     };

    $scope.destroy = function() {
        var result;
        if($scope.destroyMultipleInstances()){
           destroySelected();
        }
        else{
            deprovision(instance);
        }
        $modalInstance.close(markedInstances);
    }
    $scope.cancel = function() {
        $modalInstance.dismiss('cancel');
    };
});
