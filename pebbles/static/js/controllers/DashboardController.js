/* global app */
app.controller('DashboardController', ['$q', '$scope', '$interval', 'AuthService', 'Restangular', 'isUserDashboard',
                              function ($q,   $scope,   $interval,   AuthService,   Restangular,   isUserDashboard) {
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


        $scope.updateInstanceList = function() {
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
                $scope.instances = response;
            });
        };

        $scope.toggleAdvancedOptions = function() {
            $scope.showAdvancedOptions = ! $scope.showAdvancedOptions;
            if (! $scope.showAdvancedOptions) {
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
            instance.remove();
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
