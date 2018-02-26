app.directive('pbNotifications', ['Restangular', 'AuthService', 'config', '$interval', 'DesktopNotifications', function(Restangular, AuthService, config, $interval, DesktopNotifications) {
    return {
        restrict: 'E',
        templateUrl: config.partialsDir + '/broadcast_block.html',
        link: function(scope) {
            var notifications = Restangular.all('notifications');
            var updateNotifications = function() {
                notifications.getList().then(function(response) {
                    if (response.length) {
                        scope.selectedNotification = response[0];
                    } else {
                        scope.selectedNotification = undefined;
                    }
                });
            };
            scope.markAsSeen = function(notification) {
                notification.patch().then(updateNotifications);
            };

            scope.$on('userLoggedIn', function() {
                updateNotifications();
            });

            scope.$on('userLoggedOut', function() {
                scope.selectedNotification = undefined;
            });

            if (AuthService.isAuthenticated()) {
               updateNotifications();
            }

	    /* To send new notifications also as desktop notifications */
            var stop;
            scope.startPolling = function() {
                if (angular.isDefined(stop)) {
                    return;
                }
                stop = $interval(function () {
                if (AuthService.isAuthenticated()) {
                    notifications.getList({show_recent: true}).then(function(response) {
                        var newnotifications = response.plain();
                        if(response.length) {
                            for(i = response.length-1; i>=0; i--) {
                                DesktopNotifications.notifyNotifications(newnotifications[i]);
                            }
                        }
                    });
                }
                else {
                    $interval.cancel(stop);
                }
                }, 59000);
            };

            scope.stopPolling = function() {
               if (angular.isDefined(stop)) {
                   $interval.cancel(stop);
                   stop = undefined;
               }
            };

            scope.$on('$destroy', function() {
               scope.stopPolling();
            });

            scope.startPolling();

        }
    };
}]);
