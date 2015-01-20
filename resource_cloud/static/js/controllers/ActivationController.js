app.controller('ActivationController', ['$scope', '$location', 'Restangular', function($scope, $location, Restangular) {
    var activations = Restangular.all('activations');

    $scope.activate_user = function() {
        /* XXX: Implement activation
        activations.post(parameters).then(function(response) {
        });
        */
    };
}]);
