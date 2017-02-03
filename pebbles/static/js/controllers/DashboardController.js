/* global app */
app.controller('DashboardController', ['$q', '$scope', '$interval', 'AuthService', '$uibModal', 'Restangular', 'isUserDashboard',
                              function ($q,   $scope,   $interval,   AuthService,  $uibModal,  Restangular,   isUserDashboard) {
        Restangular.setDefaultHeaders({token: AuthService.getToken()});
        var LIMIT_DEFAULT = 100, OFFSET_DEFAULT=0;

        var blueprints = Restangular.all('blueprints');
        blueprints.getList().then(function (response) {
            $scope.blueprints = response;
        });

        var keypairs = Restangular.all('users/' + AuthService.getUserId() + '/keypairs');
        keypairs.getList().then(function (response) {
            $scope.keypairs = response;
        });

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
            if (AuthService.isGroupOwnerOrAdmin() && isUserDashboard) {
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

        $scope.keypair_exists = function() {
            if ($scope.keypairs && $scope.keypairs.length > 0) {
                return true;
            }
            return false;
        };

        $scope.maxInstanceLimitReached = function(blueprint) {
            var max_instance_limit = blueprint.full_config['maximum_instances_per_user'];
            var own_instances = _.filter($scope.instances, {'user_id': AuthService.getUserId()});
            var instance_counts = _.countBy(own_instances, 'blueprint_id');
            var running_instances = instance_counts[blueprint.id];
            if (typeof running_instances == 'undefined') {
                running_instances = 0;
            }
            if (running_instances < max_instance_limit) {
                return false;
            }
            return true;
        };

        $scope.showMaxInstanceLimitInfo = function() {
            $.notify({title: 'LAUNCH BUTTON DISABLED : ', message: 'Maximum number of running instances for the selected blueprint reached'}, {type: 'danger'});
        }

        $scope.provision = function (blueprint) {
            instances.post({blueprint: blueprint.id}).then(function (response) {
                $scope.updateInstanceList();
            }, function(response) {
                if (response.status != 409) {
                    $.notify({title: 'HTTP ' + response.status, message: 'unknown error'}, {type: 'danger'});
                } else {
                    if (response.data.error == 'USER_OVER_QUOTA') {
                        $.notify({title: 'HTTP ' + response.status, message: 'User quota exceeded, contact your administrator in order to get more'}, {type: 'danger'});
                    } else if (response.data.error == 'USER_BLOCKED') {
                        $.notify({title: 'HTTP ' + response.status, message: 'You have been blocked, contact your administrator'}, {type: 'danger'});
                    } else {
                        $.notify({title: 'HTTP ' + response.status, message: 'Maximum number of running instances for the selected blueprint reached.'}, {type: 'danger'});
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
