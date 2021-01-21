app.directive('pbMessages', ['Restangular', 'AuthService', 'config', '$interval', 'DesktopNotifications',
                     function(Restangular,   AuthService,   config,   $interval,   DesktopNotifications) {
    return {
        restrict: 'E',
        templateUrl: config.partialsDir + '/broadcast_block.html',
        link: function(scope) {
            var messages = Restangular.all('messages');
            var updateMessages = function() {
                messages.getList().then(function(response) {
                    if (response.length) {
                        scope.selectedMessage = response[0];
                    } else {
                        scope.selectedMessage = undefined;
                    }
                });
            };
            scope.markAsSeen = function(message) {
                message.patch().then(updateMessages);
            };

            scope.$on('userLoggedIn', function() {
                updateMessages();
            });

            scope.$on('userLoggedOut', function() {
                scope.selectedMessage = undefined;
            });

            if (AuthService.isAuthenticated()) {
               updateMessages();
            }

	    /* To send new messages also as desktop notifications */
            var stop;
            scope.startPolling = function() {
                if (angular.isDefined(stop)) {
                    return;
                }
                stop = $interval(function () {
                if (AuthService.isAuthenticated()) {
                    messages.getList({show_unread: true}).then(function(response) {
                        var newMessages = response.plain();
                        if(response.length) {
                            for(i = response.length-1; i>=0; i--) {
                                DesktopNotifications.notifyNotifications(newMessages[i]);
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
