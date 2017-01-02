app.directive('pbNotifications', ['Restangular', 'AuthService', 'config', function(Restangular, AuthService, config) {
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
        }
    };
}]);
