app.directive('pbNotifications', ['Restangular', 'AuthService', 'config', function(Restangular, AuthService, config) {
    return {
        restrict: 'E',
        templateUrl: config.partialsDir + '/broadcast_block.html',
        link: function(scope, element, attrs) {
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

            scope.$on('userLoggedIn', function(event) {
                updateNotifications();
            });

            if (AuthService.isAuthenticated()) {
               updateNotifications();
            }
        }
    };
}]);
