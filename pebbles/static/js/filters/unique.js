app.filter('unique', function () {
  return function (input, sort_field) {
    var unique_item = [];
    if (input) {
    	return _.uniqBy(input,function(unique_item) {
      	   return unique_item[sort_field];
        });
    };
  };
});
